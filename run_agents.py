import os
import json
from collections import Counter, defaultdict
from typing import List, Dict, Any, Tuple

from agents.agent import Agent
from agents.prompts import (
    OPERATIVE_SYSTEM_PROMPT,
    OPERATIVE_USER_PROMPT,
    SPYMASTER_SYSTEM_PROMPT,
    SPYMASTER_USER_PROMPT,
)

from engine.game_main import CodenamesGame, GameStateResponse


def _name(val: Any) -> str:
    """Return enum name or value as a plain string."""
    return getattr(val, "name", str(val))


def _team_to_emoji(team: str) -> str:
    return "🟦" if team == "BLUE" else "🟥"


def format_board_for_spymaster(game: CodenamesGame) -> str:
    """Render the board using engine's visual table (spymaster view)."""
    return str(game.state.board)


def format_board_for_operatives(game: CodenamesGame) -> str:
    """Render the board using engine's visual table (operative view)."""
    return str(game.state.board.censored)


def remaining_words_for_team(state: GameStateResponse, team: Any) -> int:
    team_s = _name(team)
    if team_s == "BLUE":
        return state.score.blue.unrevealed
    return state.score.red.unrevealed


def build_spymaster(team_name: str, model: str) -> Agent:
    return Agent(
        name=f"{team_name}-spymaster",
        system_prompt=SPYMASTER_SYSTEM_PROMPT,
        role="spymaster",
        model=model,
        max_iterations=8,
    )


def build_operatives(team_name: str, model: str, n: int = 3) -> List[Agent]:
    agents: List[Agent] = []
    for i in range(n):
        agents.append(
            Agent(
                name=f"{team_name}-op-{i + 1}",
                system_prompt=OPERATIVE_SYSTEM_PROMPT,
                role="operative",
                model=model,
                max_iterations=8,
            )
        )
    return agents


def spymaster_turn(
    game: CodenamesGame,
    spymaster: Agent,
    message_history: List[Dict[str, str]],
) -> Tuple[bool, Dict[str, Any]]:
    """Handle a single spymaster turn. Returns (success, result_dict)."""
    # Build spymaster view
    state = game.get_state(show_colors=True)
    board_str = format_board_for_spymaster(game)
    team = _name(state.current_turn.team)
    team_emoji = _team_to_emoji(team)
    opponent_emoji = _team_to_emoji("RED") if team == "BLUE" else _team_to_emoji("BLUE")
    remaining = remaining_words_for_team(state, team)
    user_msg = SPYMASTER_USER_PROMPT.format(
        team=team,
        team_emoji=team_emoji,
        opponent_emoji=opponent_emoji,
        board=board_str,
        remaining_words=remaining,
    )

    print(f"Spymaster user message: {user_msg}")

    result, assistant_msg, _, _ = spymaster.run(
        user_message=user_msg, message_history=message_history
    )
    # PRINT HIDDEN REASONING IF IT EXISTS (skip empty/None)
    _reason = assistant_msg.get("reasoning_content") or assistant_msg.get("content")
    if _reason:
        print(f"[{spymaster.name}] reasoning: {_reason}")
    if result.get("type") != "hint":
        return False, {"reason": f"unexpected result: {result}"}

    clue = result.get("clue")
    qty = int(result.get("quantity", 1))
    try:
        hint_res = game.give_hint(word=clue, card_amount=qty)
    except Exception as e:  # pylint: disable=broad-except
        return False, {"reason": f"hint rejected: {e}", "clue": clue, "quantity": qty}
    if not hint_res.success:
        return False, {
            "reason": hint_res.reason or "hint not applied",
            "clue": clue,
            "quantity": qty,
        }
    return True, {"clue": clue, "quantity": qty}


def collect_majority_vote(votes: List[str], quorum: int) -> str | None:
    if not votes:
        return None
    counts = Counter(v.lower().strip() for v in votes)
    top_word, top_count = counts.most_common(1)[0]
    if top_count > quorum // 2:
        return top_word
    return None


def guesser_turn(
    game: CodenamesGame,
    ops: List[Agent],
    message_history: List[Dict[str, str]],
    max_rounds: int = 25,
) -> None:
    """Coordinate operative discussion and majority voting for guesses until turn ends or pass."""
    team_turn = game.get_current_turn().team
    while True:
        # Refresh state for display and constraints
        board_str = format_board_for_operatives(game)
        last_hint = game.get_last_hint()
        if last_hint is None:
            return

        votes_by_agent: Dict[str, str] = {}

        def formatted_votes() -> str:
            if not votes_by_agent:
                return "(none)"
            return ", ".join(
                f"{agent_name}: {'PASS' if vote.lower() == 'pass' else vote.upper()}"
                for agent_name, vote in votes_by_agent.items()
            )

        # Iterate limited discussion/voting rounds to reach majority
        for round_i in range(max_rounds):
            # Show current board and clue at the start of each discussion round
            print("\n=== Guesser Discussion Round", round_i + 1, "===")
            print("Board (spectator view - uncensored):")
            print(format_board_for_spymaster(game))
            print(f"Clue: {last_hint.word.upper()} {last_hint.card_amount}")
            for agent in ops:
                votes_display = formatted_votes()
                user_msg = OPERATIVE_USER_PROMPT.format(
                    team=_name(team_turn),
                    board=board_str,
                    clue=last_hint.word,
                    number=last_hint.card_amount,
                    left_guesses=game.get_current_turn().left_guesses,
                    votes=votes_display,
                )

                print(f"Operative user message: {user_msg}")

                result, assistant_msg, _, _ = agent.run(
                    user_message=user_msg, message_history=message_history
                )
                # PRINT HIDDEN REASONING IF IT EXISTS (skip empty/None)
                _reason = assistant_msg.get("reasoning_content") or assistant_msg.get(
                    "content"
                )
                if _reason:
                    print(f"[{agent.name}] reasoning: {_reason}")
                if result.get("type") == "talk":
                    talk_msg = result.get("message", "")
                    message_history.append(
                        {"role": "assistant", "content": f"{agent.name}: {talk_msg}"}
                    )
                    print(f"[{agent.name}] {talk_msg}")
                elif result.get("type") == "vote":
                    word = str(result.get("word", "")).strip()
                    if word:
                        previous_vote = votes_by_agent.get(agent.name)
                        votes_by_agent[agent.name] = word
                        changed = (
                            previous_vote is not None
                            and previous_vote.lower() != word.lower()
                        )
                        reaffirmed = (
                            previous_vote is not None
                            and previous_vote.lower() == word.lower()
                        )
                        suffix = (
                            " (updated)"
                            if changed
                            else (" (unchanged)" if reaffirmed else "")
                        )
                        print(f"[{agent.name}] votes: {word.upper()}{suffix}")
                elif result.get("type") == "pass":
                    # Treat 'pass' as a vote option; require majority like word guesses
                    previous_vote = votes_by_agent.get(agent.name)
                    votes_by_agent[agent.name] = "pass"
                    changed = (
                        previous_vote is not None and previous_vote.lower() != "pass"
                    )
                    reaffirmed = (
                        previous_vote is not None and previous_vote.lower() == "pass"
                    )
                    suffix = (
                        " (updated)"
                        if changed
                        else (" (unchanged)" if reaffirmed else "")
                    )
                    print(f"[{agent.name}] votes: PASS{suffix}")
                else:
                    # Ignore unknown result types
                    pass

                # Check majority after each action
                majority = collect_majority_vote(
                    list(votes_by_agent.values()), quorum=len(ops)
                )
                if majority:
                    if majority == "pass":
                        # Majority agrees to pass
                        vote_summary = formatted_votes()
                        try:
                            _ = game.pass_turn()
                        except Exception as e:  # pylint: disable=broad-except
                            message_history.append(
                                {
                                    "role": "assistant",
                                    "content": f"system: pass failed: {e}",
                                }
                            )
                            print(f"Pass failed: {e}")
                        else:
                            message_history.append(
                                {
                                    "role": "assistant",
                                    "content": f"system: team decided to PASS; votes={vote_summary}",
                                }
                            )
                            print("Team reached majority to PASS. Passing turn.")
                        votes_by_agent.clear()
                        return
                    else:
                        guess_word = majority
                        vote_summary = formatted_votes()
                        try:
                            guess_res = game.make_guess(word=guess_word)
                        except Exception as e:  # pylint: disable=broad-except
                            message_history.append(
                                {
                                    "role": "assistant",
                                    "content": f"system: guess '{guess_word}' failed: {e}",
                                }
                            )
                            print(f"Guess '{guess_word.upper()}' failed: {e}")
                            return

                        # Log outcome
                        correctness = "correct" if guess_res.correct else "wrong"
                        message_history.append(
                            {
                                "role": "assistant",
                                "content": f"system: guessed {guess_word.upper()} -> {correctness}; left_guesses={guess_res.left_guesses}",
                            }
                        )
                        print(
                            f"Guess -> {guess_word.upper()} ({correctness}); left_guesses={guess_res.left_guesses}"
                        )
                        if vote_summary != "(none)":
                            message_history.append(
                                {
                                    "role": "assistant",
                                    "content": f"system: vote summary -> {vote_summary}",
                                }
                            )
                        # Show updated board after guess
                        print("Board (spectator view - uncensored) after guess:")
                        print(format_board_for_spymaster(game))

                        # If game ended or turn switched (wrong or out of guesses), break out
                        if guess_res.is_game_over:
                            return

                        # After a correct guess, if still this team's guess turn continues automatically
                        ct = game.get_current_turn()
                        if (
                            _name(ct.team) != _name(team_turn)
                            or _name(ct.role) != "GUESSER"
                        ):
                            return

                        # Continue to next guess in same turn
                        votes_by_agent.clear()
                        break  # break inner loop to start a new guess cycle within same turn

        # Reached here with no majority across all rounds -> pass the turn
        try:
            _ = game.pass_turn()
        except Exception as e:  # pylint: disable=broad-except
            message_history.append(
                {"role": "assistant", "content": f"system: pass failed: {e}"}
            )
            print(f"Pass failed: {e}")
        else:
            print("No majority reached after multiple rounds. Passing turn.")
        return


def main():
    model = os.environ.get("MODEL", "gpt-4.1")
    team_sizes = int(os.environ.get("OPERATIVES_PER_TEAM", "3"))
    seed = int(os.environ.get("SEED", "42"))

    game = CodenamesGame(board_size=25, seed=seed)

    # Build agents for both teams
    blue_spy = build_spymaster("blue", model)
    red_spy = build_spymaster("red", model)
    blue_ops = build_operatives("blue", model, n=team_sizes)
    red_ops = build_operatives("red", model, n=team_sizes)

    # Simple per-team chat history for operatives and spymasters
    # Use normalized team name ("BLUE"/"RED") as keys to avoid enum/string mismatches
    operative_histories: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    spymaster_histories: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    # Main game loop
    print(f"Starting Codenames game: {game}")
    while not game.is_game_over():
        state = game.get_state(show_colors=False)
        turn = state.current_turn
        team = turn.team
        team_key = _name(team)

        if _name(turn.role) == "HINTER":
            spy = blue_spy if team_key == "BLUE" else red_spy
            print(f"Spymaster history: {spymaster_histories[team_key]}")
            ok, info = spymaster_turn(game, spy, spymaster_histories[team_key])
            if not ok:
                print(f"Spymaster error for {team_key}: {info}")
                # If spymaster fails, try to pass turn to avoid deadlock
                try:
                    _ = game.pass_turn()
                except Exception:
                    break
            else:
                print("\n=== Spymaster Turn ===")
                print(
                    f"Team {team_key} spymaster gave hint: {info['clue']} {info['quantity']}"
                )
                # Show full board for spectators
                print("Board (spectator view - uncensored):")
                print(format_board_for_spymaster(game))
        else:
            ops = blue_ops if team_key == "BLUE" else red_ops
            print("\n=== Guesser Turn ===")
            guesser_turn(game, ops, operative_histories[team_key])

        # Print a light summary of board progress
        s = game.get_state(show_colors=False)
        print(
            f"Turn -> {_name(s.current_turn.team)}/{_name(s.current_turn.role)}; "
            f"Blue remaining={s.score.blue.unrevealed}, Red remaining={s.score.red.unrevealed}"
        )

    # Final state
    final = game.get_state(show_colors=True)
    print("Game over!")
    if final.winner:
        print(f"Winner: {_name(final.winner.team_color)}")
    print(json.dumps(final.dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
