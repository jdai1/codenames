"""Pydantic schemas for API responses."""

from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel

from engine.game.card import Card
from engine.game.color import TeamColor, CardColor
from engine.game.player import PlayerRole
from engine.game.move import GivenHint
from engine.game.state import Score
from engine.game.winner import Winner


class ReasoningTokenType(str, Enum):
    """Types of reasoning tokens from AI agents."""
    GIVE_HINT_REASONING = "give-hint-reasoning"
    MAKE_GUESS_REASONING = "make-guess-reasoning"
    GIVE_HINT_RESULT = "give-hint-result"
    MAKE_GUESS_RESULT = "make-guess-result"
    ERROR = "error"


class ReasoningToken(BaseModel):
    """A reasoning token from an AI agent."""
    type: ReasoningTokenType
    content: Any  # Can be string (for reasoning), dict (for results), etc.

    class Config:
        use_enum_values = True


class CardWithIndex(BaseModel):
    """Card with its board index."""
    index: int
    word: str
    color: Optional[CardColor]
    revealed: bool

    class Config:
        use_enum_values = True


class TurnInfo(BaseModel):
    """Information about current turn."""
    team: TeamColor
    role: PlayerRole
    left_guesses: int

    class Config:
        use_enum_values = True


class HintResult(BaseModel):
    """Result of giving a hint."""
    success: bool
    hint: Optional[GivenHint] = None
    left_guesses: int = 0
    reason: Optional[str] = None

    class Config:
        use_enum_values = True


class GuessResult(BaseModel):
    """Result of making a guess."""
    success: bool
    guessed_card: Optional[Card] = None
    correct: Optional[bool] = None
    left_guesses: int = 0
    is_game_over: bool = False
    winner: Optional[Winner] = None
    reason: Optional[str] = None

    class Config:
        use_enum_values = True


class PassResult(BaseModel):
    """Result of passing turn."""
    success: bool
    action: str
    next_team: TeamColor

    class Config:
        use_enum_values = True


class GameStateResponse(BaseModel):
    """Complete game state."""
    game_id: str
    board: List[CardWithIndex]
    score: Score
    current_turn: TurnInfo
    hints: List[GivenHint]
    last_hint: Optional[GivenHint]
    is_game_over: bool
    winner: Optional[Winner]
    board_size: int

    class Config:
        use_enum_values = True
