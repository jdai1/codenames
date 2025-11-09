from typing import Optional

from agents.tool import Tool
from pydantic import BaseModel


class HintArguments(BaseModel):
    clue: str
    quantity: int
    reasoning: Optional[str] = None


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
        result = {
            "type": "hint",
            "clue": arguments.clue,
            "quantity": arguments.quantity,
        }
        if arguments.reasoning is not None:
            result["reasoning"] = arguments.reasoning
        return result
