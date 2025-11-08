"""Internal Python API for Codenames game operations."""

import re
from typing import Optional, List
from uuid import uuid4

from engine.boards.builder import generate_board, SupportedLanguage
from engine.game.state import GameState, new_game_state
from engine.game.move import Hint, Guess, PASS_GUESS
from engine.game.player import PlayerRole
from engine.game.color import CardColor
from engine.game.exceptions import CardNotFoundError
from engine.schema import (
    CardWithIndex,
    TurnInfo,
    HintResult,
    GuessResult,
    PassResult,
    GameStateResponse,
)


# ===== Utility Functions =====


def sanitize_word(word: str) -> str:
    """
    Sanitize a word to only contain lowercase English letters and spaces.

    Args:
        word: The word to sanitize

    Returns:
        Sanitized word (lowercase, only letters and spaces)

    Raises:
        ValueError: If word contains invalid characters
    """
    # Remove leading/trailing whitespace
    word = word.strip()

    # Check if word only contains letters and spaces
    if not re.match(r"^[a-zA-Z\s]+$", word):
        raise ValueError(f"Word must only contain English letters and spaces: '{word}'")

    # Convert to lowercase and normalize spaces
    word = word.lower()
    word = re.sub(r"\s+", " ", word)  # Replace multiple spaces with single space

    return word


# ===== Main API =====


class CodenamesGame:
    """Main API interface for a Codenames game."""

    def __init__(
        self,
        language: str = "english",
        board_size: int = 25,
        seed: Optional[int] = None,
    ):
        """
        Create a new Codenames game.

        Args:
            language: Board language ("english" or "hebrew")
            board_size: Number of cards (default 25)
            seed: Random seed for reproducibility
        """
        self.game_id = str(uuid4())
        board = generate_board(
            language=SupportedLanguage.ENGLISH, board_size=board_size, seed=seed
        )
        self.state = new_game_state(board=board)

    # ===== Game State Queries =====

    def get_board(self, show_colors: bool = False) -> List[CardWithIndex]:
        """
        Get all cards on the board.

        Args:
            show_colors: If True, show all colors (spymaster view).
                        If False, only show revealed cards (operative view).

        Returns:
            List of cards with indices
        """
        board = self.state.board if show_colors else self.state.board.censored
        return [
            CardWithIndex(
                index=i, word=card.word, color=card.color, revealed=card.revealed
            )
            for i, card in enumerate(board.cards)
        ]

    def get_card(self, index: int, show_color: bool = False) -> CardWithIndex:
        """
        Get a specific card by index.

        Args:
            index: Card index (0 to board_size-1)
            show_color: Whether to show the card's color

        Returns:
            Card with index
        """
        if index < 0 or index >= len(self.state.board.cards):
            raise ValueError(f"Invalid card index: {index}")

        card = self.state.board.cards[index]
        if not show_color and not card.revealed:
            card = card.censored

        return CardWithIndex(
            index=index, word=card.word, color=card.color, revealed=card.revealed
        )

    def get_score(self):
        """
        Get current game score.

        Returns:
            Score with blue/red team scores
        """
        return self.state.score

    def get_current_turn(self) -> TurnInfo:
        """
        Get information about whose turn it is.

        Returns:
            Current turn info
        """
        return TurnInfo(
            team=self.state.current_team_color,
            role=self.state.current_player_role,
            left_guesses=self.state.left_guesses,
        )

    def get_hints(self):
        """
        Get all hints given so far.

        Returns:
            List of given hints
        """
        return self.state.given_hints

    def get_last_hint(self):
        """Get the most recent hint, or None if no hints given."""
        if not self.state.given_hints:
            return None
        return self.state.given_hints[-1]

    def is_game_over(self) -> bool:
        """Check if the game has ended."""
        return self.state.is_game_over

    def get_winner(self):
        """
        Get the winner if game is over.

        Returns:
            Winner info or None if game not over
        """
        return self.state.winner

    def get_state(self, show_colors: bool = False) -> GameStateResponse:
        """
        Get complete game state in one call.

        Args:
            show_colors: If True, show all card colors (spymaster view).
                        If False, only show revealed cards (operative view).

        Returns:
            Complete game state
        """
        return GameStateResponse(
            game_id=self.game_id,
            board=self.get_board(show_colors=show_colors),
            score=self.get_score(),
            current_turn=self.get_current_turn(),
            hints=self.get_hints(),
            last_hint=self.get_last_hint(),
            is_game_over=self.is_game_over(),
            winner=self.get_winner(),
            board_size=len(self.state.board.cards),
        )

    # ===== Game Actions =====

    def give_hint(self, word: str, card_amount: int) -> HintResult:
        """
        Give a hint (spymaster action).

        Args:
            word: The hint word
            card_amount: Number of cards the hint refers to

        Returns:
            Hint result

        Raises:
            ValueError if not hinter's turn or invalid hint
        """
        if self.state.current_player_role != PlayerRole.HINTER:
            raise ValueError("Not the hinter's turn")

        hint = Hint(word=word, card_amount=card_amount)
        given_hint = self.state.process_hint(hint)

        if given_hint is None:
            return HintResult(success=False, reason="quit")

        return HintResult(
            success=True, hint=given_hint, left_guesses=self.state.left_guesses
        )

    def make_guess(self, word: str) -> GuessResult:
        """
        Make a guess (operative action).

        Args:
            word: The word on the card to guess

        Returns:
            Guess result including whether guess was correct

        Raises:
            ValueError: If not guesser's turn, word not on board, or invalid word format
        """
        if self.state.current_player_role != PlayerRole.GUESSER:
            raise ValueError("Not the guesser's turn")

        # Sanitize the word
        try:
            sanitized_word = sanitize_word(word)
        except ValueError as e:
            raise ValueError(f"Invalid word format: {e}")

        # Find the card index
        try:
            card_index = self.state.board.find_card_index(sanitized_word)
        except CardNotFoundError:
            raise ValueError(f"Word '{word}' is not on the board")

        # Make the guess
        guess = Guess(card_index=card_index)
        given_guess = self.state.process_guess(guess)

        if given_guess is None:
            return GuessResult(success=False, reason="pass or quit")

        return GuessResult(
            success=True,
            guessed_card=given_guess.guessed_card,
            correct=given_guess.correct,
            left_guesses=self.state.left_guesses,
            is_game_over=self.state.is_game_over,
            winner=self.get_winner(),
        )

    def pass_turn(self) -> PassResult:
        """
        Pass the turn (operative decides to stop guessing).

        Returns:
            Pass result
        """
        if self.state.current_player_role != PlayerRole.GUESSER:
            raise ValueError("Can only pass during guesser's turn")

        guess = Guess(card_index=PASS_GUESS)
        self.state.process_guess(guess)

        return PassResult(
            success=True, action="passed", next_team=self.state.current_team_color
        )

    # ===== Utility Methods =====

    def get_unrevealed_cards(self, color: Optional[str] = None):
        """
        Get all unrevealed cards, optionally filtered by color.

        Args:
            color: Optional color filter ("RED", "BLUE", "GRAY", "BLACK")

        Returns:
            List of unrevealed cards
        """
        cards = self.state.board.unrevealed_cards
        if color:
            card_color = CardColor[color.upper()]
            cards = tuple(c for c in cards if c.color == card_color)

        return list(cards)

    def get_revealed_cards(self, color: Optional[str] = None):
        """
        Get all revealed cards, optionally filtered by color.

        Args:
            color: Optional color filter ("RED", "BLUE", "GRAY", "BLACK")

        Returns:
            List of revealed cards
        """
        cards = self.state.board.revealed_cards
        if color:
            card_color = CardColor[color.upper()]
            cards = tuple(c for c in cards if c.color == card_color)

        return list(cards)

    def __repr__(self) -> str:
        turn = self.get_current_turn()
        return f"CodenamesGame(id={self.game_id[:8]}, turn={turn.team}/{turn.role})"
