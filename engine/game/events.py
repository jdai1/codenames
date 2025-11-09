from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from engine.game.base import BaseModel
from engine.game.color import TeamColor
from engine.game.move import GivenGuess, GivenHint
from engine.game.player import PlayerRole


class ActorType(str, Enum):
    """Type of actor performing the action."""
    USER = "user"
    LLM = "llm"


class Actor(BaseModel):
    """Base class for actors (user or LLM)."""
    actor_type: ActorType
    name: str


class UserActor(Actor):
    """Represents a human user."""
    actor_type: ActorType = ActorType.USER


class LLMActor(Actor):
    """Represents an LLM agent."""
    actor_type: ActorType = ActorType.LLM
    model: str  # e.g., "gpt-4", "claude-3-opus", etc.

    def __str__(self) -> str:
        return f"{self.name} ({self.model})"


class EventType(str, Enum):
    """Types of events that can occur in the game."""
    HINT_GIVEN = "hint_given"
    GUESS_MADE = "guess_made"
    TURN_PASSED = "turn_passed"
    CHAT_MESSAGE = "chat_message"


class GameEvent(BaseModel):
    """Base event that tracks any action in the game."""
    event_type: EventType
    team_color: TeamColor
    player_role: PlayerRole
    actor: Union[UserActor, LLMActor]
    timestamp: datetime = None

    def __init__(self, **data):
        if 'timestamp' not in data or data['timestamp'] is None:
            data['timestamp'] = datetime.now()
        super().__init__(**data)


class HintEvent(GameEvent):
    """Event for when a hint is given."""
    event_type: EventType = EventType.HINT_GIVEN
    hint: GivenHint

    def __str__(self) -> str:
        actor_str = str(self.actor) if isinstance(self.actor, LLMActor) else self.actor.name
        return f"[{self.team_color.value}] {actor_str} Hint: {self.hint}"


class GuessEvent(GameEvent):
    """Event for when a guess is made."""
    event_type: EventType = EventType.GUESS_MADE
    guess: GivenGuess

    def __str__(self) -> str:
        actor_str = str(self.actor) if isinstance(self.actor, LLMActor) else self.actor.name
        return f"[{self.team_color.value}] {actor_str} Guess: {self.guess}"


class PassEvent(GameEvent):
    """Event for when a team passes their turn."""
    event_type: EventType = EventType.TURN_PASSED

    def __str__(self) -> str:
        actor_str = str(self.actor) if isinstance(self.actor, LLMActor) else self.actor.name
        return f"[{self.team_color.value}] {actor_str} Passed turn"


class ChatEvent(GameEvent):
    """Event for LLM agent chat messages."""
    event_type: EventType = EventType.CHAT_MESSAGE
    message: str
    message_metadata: Optional[Dict] = None  # Can store reasoning, tool calls, etc.

    def __str__(self) -> str:
        actor_str = str(self.actor) if isinstance(self.actor, LLMActor) else self.actor.name
        return f"[{self.team_color.value}] {actor_str} ({self.player_role.value}): {self.message}"


class TeamHistory(BaseModel):
    """Tracks all events for a specific team."""
    team_color: TeamColor
    hints_given: List[HintEvent] = []
    guesses_made: List[GuessEvent] = []
    chat_messages: List[ChatEvent] = []
    passes: List[PassEvent] = []
    all_events: List[GameEvent] = []

    def add_hint(self, hint_event: HintEvent) -> None:
        """Add a hint event to team history."""
        self.hints_given.append(hint_event)
        self.all_events.append(hint_event)

    def add_guess(self, guess_event: GuessEvent) -> None:
        """Add a guess event to team history."""
        self.guesses_made.append(guess_event)
        self.all_events.append(guess_event)

    def add_chat(self, chat_event: ChatEvent) -> None:
        """Add a chat message to team history."""
        self.chat_messages.append(chat_event)
        self.all_events.append(chat_event)

    def add_pass(self, pass_event: PassEvent) -> None:
        """Add a pass event to team history."""
        self.passes.append(pass_event)
        self.all_events.append(pass_event)

    def get_recent_events(self, count: int = 10) -> List[GameEvent]:
        """Get the most recent N events."""
        return self.all_events[-count:]

    def get_chat_history(self) -> List[ChatEvent]:
        """Get all chat messages in chronological order."""
        return self.chat_messages


class GameHistory(BaseModel):
    """Tracks complete game history across all teams."""
    blue_team: TeamHistory
    red_team: TeamHistory
    global_events: List[GameEvent] = []

    def __init__(self, **data):
        if 'blue_team' not in data:
            data['blue_team'] = TeamHistory(team_color=TeamColor.BLUE)
        if 'red_team' not in data:
            data['red_team'] = TeamHistory(team_color=TeamColor.RED)
        super().__init__(**data)

    def get_team_history(self, team_color: TeamColor) -> TeamHistory:
        """Get history for a specific team."""
        return self.blue_team if team_color == TeamColor.BLUE else self.red_team

    def add_event(self, event: GameEvent) -> None:
        """Add an event to the appropriate team history and global history."""
        team_history = self.get_team_history(event.team_color)

        if isinstance(event, HintEvent):
            team_history.add_hint(event)
        elif isinstance(event, GuessEvent):
            team_history.add_guess(event)
        elif isinstance(event, ChatEvent):
            team_history.add_chat(event)
        elif isinstance(event, PassEvent):
            team_history.add_pass(event)
        else:
            team_history.all_events.append(event)

        self.global_events.append(event)

    def get_all_events(self) -> List[GameEvent]:
        """Get all events in chronological order."""
        return self.global_events

    def get_chat_history_for_team(self, team_color: TeamColor) -> List[ChatEvent]:
        """Get all chat messages for a specific team."""
        return self.get_team_history(team_color).get_chat_history()
