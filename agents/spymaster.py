from typing import List, Dict, Any
import json
from openai import OpenAI
from agents.tool import Tool
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HintArguments(BaseModel):
    clue: str
    quantity: int


class HintTool(Tool):
    """Tool for the agent to vote for the next guess"""

    Arguments = HintArguments

    @property
    def name(self) -> str:
        return "hint_tool"

    @property
    def description(self) -> str:
        return "Give a hint to the operatives and the number of words on the board that relate to that hint."

    def execute(self, arguments: HintArguments) -> dict:
        """
        Give a hint to the operatives and the number of words on the board that relate to that hint.
        """
        return {
            "type": "hint",
            "clue": arguments.clue,
            "quantity": arguments.quantity,
        }


class SpymasterAgent:
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
        self.tools = tools or [HintTool()]
        self.model = model
        self.max_iterations = max_iterations

    def run(
        self, user_message: str, message_history: List[Dict[str, str]]
    ) -> dict[str, str]:
        """
        Given past messages in the history, and the state of the board (inside of user message),
        Either say something to rest of the models,
        Or call a tool to give a hint to the operatives and the number of words on the board that relate to that hint.
        """
        client = OpenAI()

        # Build the messages list
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(message_history)
        messages.append({"role": "user", "content": user_message})

        # Convert tools to OpenAI format
        openai_tools = [tool.to_openai_tool() for tool in self.tools]

        # Make the API call
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
        )

        message = response.choices[0].message

        # Check if the agent wants to use a tool
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name

            # Find the matching tool
            for tool in self.tools:
                if hasattr(tool, "Name") and tool.Name == tool_name:
                    # Parse the arguments and execute
                    args = json.loads(tool_call.function.arguments)
                    result = tool.execute(**args)

                    return {
                        "type": "tool_call",
                        "tool": tool_name,
                        "result": result,
                        "agent": self.name,
                    }

            return {
                "type": "error",
                "error": f"Tool {tool_name} not found",
                "agent": self.name,
            }

        # Otherwise, return the message content
        return {
            "type": "message",
            "content": message.content,
            "agent": self.name,
        }
