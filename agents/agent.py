import json
import logging
from typing import Any, Dict, List

from litellm import completion, completion_cost, token_counter

from agents.operative_tools import TalkTool, VoteTool, PassTool
from agents.spymaster_tools import HintTool

logger = logging.getLogger(__name__)


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

        # Prepare tools for the model
        tool_list = [t.to_openai_tool() for t in (self.tools or [])]
        tools_by_name = {t.name: t for t in (self.tools or [])}
        model_cost = 0
        token_usage = 0
        # Iteratively allow the model to call tools and react
        for _ in range(max(1, self.max_iterations)):
            resp = completion(
                model=self.model,
                messages=messages,
                tools=tool_list if tool_list else None,
                tool_choice="auto" if tool_list else None,
                # stream=True,
            )

            model_cost = completion_cost(completion_response=resp)
            token_usage = token_counter(model=self.model, messages=messages)
            choice = resp["choices"][0]["message"]

            # Append assistant message to conversation
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": choice.get("content") or "",
            }
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
        model="gpt-4o-mini",
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
