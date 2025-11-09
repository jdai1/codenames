import json
import logging
import time
from typing import Any, Dict, List

from litellm import completion, completion_cost, token_counter

from agents.operative_tools import TalkTool, VoteTool, PassTool
from agents.spymaster_tools import HintTool
from model_names import MODEL_STRINGS

logger = logging.getLogger(__name__)


def _supports_reasoning_effort(model_id: str) -> bool:
    """
    Return True if the given canonical model_id should receive reasoning_effort,
    as indicated by MODEL_STRINGS entries which are [canonical_id, bool].
    """
    try:
        for _, entry in MODEL_STRINGS.items():
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                canonical_id, allow_reasoning = entry[0], bool(entry[1])
            else:
                canonical_id, allow_reasoning = str(entry), False
            if str(canonical_id) == str(model_id):
                return allow_reasoning
    except Exception:
        # Be conservative: if mapping lookup fails, do not send reasoning_effort
        return False
    return False


class Agent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        role: str,
        model: str,
        max_iterations: int = 30,
        tools: List[Any] = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.role = role
        if self.role == "operative" and tools is None:
            self.tools = [VoteTool(), TalkTool(), PassTool()]
        elif self.role == "spymaster" and tools is None:
            self.tools = [HintTool()]
        else:
            self.tools = tools
        self.model = model
        self.max_iterations = max_iterations

    def _is_claude_model(self) -> bool:
        """Check if the model is a Claude model."""
        model_str = str(self.model).lower()
        return "claude" in model_str

    def _fix_claude_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert messages to Claude's thinking format if needed.
        Claude requires assistant messages with thinking to have content as an array
        starting with a thinking block.
        """
        fixed_messages = []
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # If content is a string, convert to Claude's format
                if isinstance(content, str) and content:
                    # Check if there's reasoning_content to use as thinking
                    reasoning = msg.get("reasoning_content", "")
                    if reasoning:
                        # Create content blocks: thinking first, then text
                        fixed_content = [
                            {"type": "thinking", "text": reasoning},
                            {"type": "text", "text": content},
                        ]
                    else:
                        # No thinking, just text block
                        fixed_content = [{"type": "text", "text": content}]

                    fixed_msg = {**msg, "content": fixed_content}
                    # Remove reasoning_content as it's now in content blocks
                    fixed_msg.pop("reasoning_content", None)
                    fixed_messages.append(fixed_msg)
                else:
                    # Already in correct format or empty
                    fixed_messages.append(msg)
            else:
                fixed_messages.append(msg)
        return fixed_messages

    def run(
        self, user_message: str, message_history: List[Dict[str, str]]
    ) -> tuple[Dict[str, str], Dict[str, Any], float, int]:
        """
        Given past messages in the history, and the state of the board (inside of user message),
        Either say something to rest of the models,
        Or call a tool to vote for the next move.
        """

        # Build the message list: system -> prior history -> current user message
        messages: List[Dict[str, Any]] = []
        messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(message_history)
        messages.append({"role": "user", "content": user_message})

        # Convert messages to Claude's format if needed (before first API call)
        if self._is_claude_model():
            messages = self._fix_claude_messages(messages)

        # Prepare tools for the model
        tool_list = [t.to_openai_tool() for t in (self.tools or [])]
        tools_by_name = {t.name: t for t in (self.tools or [])}
        model_cost = 0
        token_usage = 0
        # Iteratively allow the model to call tools and react
        for _ in range(max(1, self.max_iterations)):
            completion_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "tools": tool_list if tool_list else None,
                "tool_choice": "auto" if tool_list else None,
            }
            if _supports_reasoning_effort(self.model):
                completion_kwargs["reasoning_effort"] = "low"
            if self.model == "grok-4-fast-reasoning":
                completion_kwargs["reasoning_effort"] = "low"
            # Retry logic: retry all errors with exponential backoff (1s, 3s, 10s)
            max_retries = 3
            backoff_delays = [1, 3, 10]  # seconds for each retry attempt
            resp = None
            for attempt in range(max_retries):
                try:
                    print("Start request")
                    resp = completion(**completion_kwargs)
                    print("resp", resp)
                    break
                except Exception as e:
                    error_str = str(e).lower()

                    # Check for Claude thinking format errors - need to fix message history
                    if "thinking" in error_str and "expected" in error_str:
                        logger.warning(
                            "Claude thinking format error detected. Attempting to fix message history..."
                        )
                        # Convert string content to Claude's content block format
                        messages = self._fix_claude_messages(messages)
                        if attempt < max_retries - 1:
                            continue

                    # Retry all errors with exponential backoff (1s, 3s, 10s)
                    wait_time = backoff_delays[attempt]
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"API error (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        # Last attempt failed, wait 10s then raise
                        logger.error(
                            f"API error (final attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Waiting {wait_time}s before raising..."
                        )
                        time.sleep(wait_time)
                        raise

            # Validate response has choices
            if not resp or "choices" not in resp or not resp["choices"]:
                error_msg = f"Empty response from {self.model}: {resp}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if self.model != "moonshot/kimi-k2-thinking":
                model_cost = completion_cost(completion_response=resp)
                token_usage = token_counter(model=self.model, messages=messages)
            choice = resp["choices"][0]["message"]

            # Append assistant message to conversation
            # For Claude models with thinking, preserve the content array format
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
            }

            # Preserve Claude's content block format if present
            content = choice.get("content")
            if isinstance(content, list):
                # Claude format: array of content blocks
                assistant_msg["content"] = content
            else:
                # Standard format: string content
                assistant_msg["content"] = content or ""

            if "tool_calls" in choice and choice["tool_calls"]:
                assistant_msg["tool_calls"] = choice["tool_calls"]
            if "reasoning_content" in choice and choice["reasoning_content"]:
                assistant_msg["reasoning_content"] = choice["reasoning_content"]
            messages.append(assistant_msg)

            # Handle tool calls if any
            tool_calls = choice.get("tool_calls")
            # Back-compat: also check for legacy single function_call
            legacy_fn_call = choice.get("function_call")

            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name")
                    raw_args = func.get("arguments") or "{}"
                    parsed_args = json.loads(raw_args)

                    tool_obj = tools_by_name.get(tool_name)
                    result = tool_obj(**parsed_args) if tool_obj else {}

                    # If the tool returns a structured action, return it
                    if isinstance(result, dict) and result.get("type") in {
                        "vote",
                        "talk",
                        "pass",
                        "hint",
                    }:
                        return result, assistant_msg, model_cost, token_usage

                    # Otherwise, feed the tool result back into the conversation and continue
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": tool_name,
                            "content": json.dumps(result),
                        }
                    )
                # Continue the loop to let the model react to tool outputs
                continue

            elif legacy_fn_call:
                # Handle legacy single function_call format
                tool_name = legacy_fn_call.get("name")
                raw_args = legacy_fn_call.get("arguments") or "{}"
                parsed_args = json.loads(raw_args)

                tool_obj = tools_by_name.get(tool_name)
                result = tool_obj(**parsed_args) if tool_obj else {}
                if isinstance(result, dict) and result.get("type") in {
                    "vote",
                    "talk",
                    "pass",
                    "hint",
                }:
                    return result, assistant_msg, model_cost, token_usage

                # Feed back and continue
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": legacy_fn_call.get("id"),
                        "name": tool_name,
                        "content": json.dumps(result),
                    }
                )
                continue

            # No tool calls -> remind the model to use tools only and continue
            messages.append(
                {
                    "role": "system",
                    "content": "You must respond by calling one of the provided tools (talk_tool, vote_tool, pass_tool, or hint_tool). Do not output plain text.",
                }
            )

        # Max iterations reached without a decisive action
        try:
            model_cost = completion_cost(completion_response=resp)
            token_usage = token_counter(model=self.model, messages=messages)
        except Exception as e:
            # logger.warning(f"Error calculating completion cost: {e}")
            print(f"Error calculating completion cost: {e}")
        return (
            {
                "type": "talk",
                "message": "Unable to proceed: no tool call produced.",
            },
            assistant_msg,
            model_cost,
            token_usage,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Create an operative agent
    agent = Agent(
        name="TestOperative",
        system_prompt="",
        role="operative",
        model="gpt-4.1",
        max_iterations=10,
    )

    # Example board state and user message
    user_message = """
The current state of the board is:
PIANO, GUITAR, DRUM, VIOLIN, TRUMPET

The current clue is:
MUSIC 3

The number of words you need to guess is:
3

The other Operatives have voted for the following words:
None yet

You must pick a tool no matter what
"""

    # Run the agent
    message_history = []
    result, assistant_msg, cost, tokens = agent.run(user_message, message_history)

    print("\n=== Agent Result ===")
    print(f"Result: {result}")
    print(f"Cost: ${cost:.4f}")
    print(f"Tokens: {tokens}")
    print(f"Assistant message: {assistant_msg}")
