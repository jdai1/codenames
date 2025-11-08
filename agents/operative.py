from typing import List, Dict, Any
from agents.tool import Tool
import logging
from pydantic import BaseModel, Field
import json
from litellm import completion

logger = logging.getLogger(__name__)


class VoteArguments(BaseModel):
    word: str = Field(description="The word to vote for")


class VoteTool(Tool):
    """Tool for the agent to vote for the next guess"""

    Arguments = VoteArguments

    @property
    def name(self) -> str:
        return "vote_tool"

    @property
    def description(self) -> str:
        return "Vote for the next guess. "

    def execute(self, arguments: VoteArguments) -> dict:
        """
        Vote for the next guess.
        If a majority of models have voted for the same word,
        the team will have selected this word in the game engine
        """
        return {
            "type": "vote",
            "word": arguments.word,
        }


class TalkArguments(BaseModel):
    message: str = Field(description="The message to talk to the other operatives")


class TalkTool(Tool):
    """Tool for the agent to talk to the other operatives"""

    Arguments = TalkArguments

    @property
    def name(self) -> str:
        return "talk_tool"

    @property
    def description(self) -> str:
        return "Talk to the other operatives. "

    def execute(self, arguments: TalkArguments) -> dict:
        """
        Talk to the other operatives.
        """
        return {
            "type": "talk",
            "message": arguments.message,
        }


class OperativeAgent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: List[Any],
        model: str,
        max_iterations: int = 30,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or [VoteTool(), TalkTool()]
        self.model = model
        self.max_iterations = max_iterations

    def run(
        self, user_message: str, message_history: List[Dict[str, str]]
    ) -> dict[str, str]:
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

        # Iteratively allow the model to call tools and react
        for _ in range(max(1, self.max_iterations)):
            resp = completion(
                model=self.model,
                messages=messages,
                tools=tool_list if tool_list else None,
                tool_choice="required" if tool_list else None,
            )

            choice = resp["choices"][0]["message"]

            # Append assistant message to conversation
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": choice.get("content"),
            }
            if "tool_calls" in choice and choice["tool_calls"]:
                assistant_msg["tool_calls"] = choice["tool_calls"]
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

                    # If the tool returns a structured action (vote/talk), return it
                    if isinstance(result, dict) and result.get("type") in {
                        "vote",
                        "talk",
                    }:
                        return result

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
                if isinstance(result, dict) and result.get("type") in {"vote", "talk"}:
                    return result

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
                    "content": "You must respond by calling one of the provided tools (talk_tool or vote_tool). Do not output plain text.",
                }
            )

        # Max iterations reached without a decisive action
        return {
            "type": "talk",
            "message": "Unable to proceed: no tool call produced.",
        }
