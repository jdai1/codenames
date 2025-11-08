from agents.tool import Tool
from pydantic import BaseModel, Field


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


class PassArguments(BaseModel):
    pass


class PassTool(Tool):
    """Tool for the agent to pass the turn (stop guessing)."""

    Arguments = PassArguments

    @property
    def name(self) -> str:
        return "pass_tool"

    @property
    def description(self) -> str:
        return "Pass the turn if the team does not want to make any more guesses."

    def execute(self, arguments: PassArguments) -> dict:
        """
        Request to pass the turn (stop guessing).
        """
        return {
            "type": "pass",
        }
