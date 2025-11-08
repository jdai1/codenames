from enum import Enum
from typing import Optional, Union

from engine.boards.english import ENGLISH_WORDS
from engine.game.board import Board
from engine.game.color import TeamColor


class SupportedLanguage(str, Enum):
    ENGLISH = "english"
    HEBREW = "hebrew"


def generate_board(
    language: Union[str, SupportedLanguage],
    board_size: int = 25,
    black_amount: int = 1,
    seed: Optional[int] = None,
    first_team: Optional[TeamColor] = None,
) -> Board:
    if language == SupportedLanguage.ENGLISH:
        words = ENGLISH_WORDS
    else:
        raise NotImplementedError(f"Unknown language: {language}")
    return Board.from_vocabulary(
        language=language,
        vocabulary=words,
        board_size=board_size,
        black_amount=black_amount,
        seed=seed,
        first_team=first_team,
    )
