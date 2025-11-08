from typing import List, Dict, Any
import json
from openai import OpenAI


class VoteTool:
    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "vote_tool",
                "description": "Vote for the upcoming guess"
                + "If a majority of models have voted for the same word,"
                + "the team will have selected this word in the game engine",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vote": {
                            "type": "string",
                            "description": "The word to vote for in the upcoming turn",
                        },
                    },
                    "required": ["vote"],
                },
            },
        }

    def execute(self, vote: str) -> Dict[str, Any]:
        """
        Execute the vote tool with the given vote.

        Args:
            vote: The word that the operative is voting for

        Returns:
            Dictionary containing the vote result
        """
        if not vote:
            return {
                "success": False,
                "error": "No vote provided. Please vote for a word.",
            }

        return {
            "success": True,
            "vote": vote,
            "message": f"Successfully voted for: {vote}",
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
        self.tools = tools or [VoteTool()]
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
