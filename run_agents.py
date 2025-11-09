import os
import json
from collections import Counter, defaultdict
from typing import List, Dict, Any, Tuple

from litellm import completion

from agents.agent import Agent
from agents.prompts import (
    OPERATIVE_SYSTEM_PROMPT,
    OPERATIVE_USER_PROMPT,
    SPYMASTER_SYSTEM_PROMPT,
    SPYMASTER_USER_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    SUMMARIZER_USER_PROMPT,
)

from engine.game_main import CodenamesGame, GameStateResponse
from engine.game.exceptions import CardNotFoundError
from engine.game.base import canonical_format
from engine.game.events import (
    LLMActor,
    SpymasterEvent,
    OperativeEvent,
    OperativeToolType,
)
from engine.game.player import PlayerRole


def _name(val: Any) -> str:
    """Return enum name or value as a plain string."""
    return getattr(val, "name", str(val))


def _team_to_emoji(team: str) -> str:
    return "🟦" if team == "BLUE" else "🟥"


# --- Quick counter for total LLM calls made from this script ---
LLM_CALLS: int = 0


def inc_llm_calls(step: str) -> None:
    global LLM_CALLS  # noqa: PLW0603
    LLM_CALLS += 1
    print(f"[LLM] total calls={LLM_CALLS} | step={step}")


def format_board_for_spymaster(game: CodenamesGame) -> str:
    """Render the board using engine's visual table (spymaster view)."""
    return str(game.state.board)


def format_board_for_operatives(game: CodenamesGame) -> str:
    """Render the board using engine's visual table (operative view)."""
    return str(game.state.board.censored)


def summarize_round_messages(
    messages: List[Dict[str, str]], model: str, max_tokens: int = 256
) -> str:
    """Summarize a single round of operative discussion for spymaster context."""
    if not messages:
        return ""

    transcript_lines: List[str] = []
    for msg in messages:
        role = msg.get("role", "assistant").upper()
        content = msg.get("content", "").strip()
        if not content:
            continue
        transcript_lines.append(f"{role}: {content}")

    if not transcript_lines:
        return ""

    user_prompt = SUMMARIZER_USER_PROMPT.format(transcript="\n".join(transcript_lines))
    summary_messages = [
        {
            "role": "system",
            "content": SUMMARIZER_SYSTEM_PROMPT.strip(),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        inc_llm_calls(step="summarizer_round_messages")
        resp = completion(
            model=model,
            messages=summary_messages,
            max_tokens=max_tokens,
        )
        return resp["choices"][0]["message"].get("content", "").strip()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Failed to summarize operative round: {exc}")
        return ""


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
    state = game.get_state(show_colors=True)
    board_str = format_board_for_spymaster(game)
    team = _name(state.current_turn.team)
    team_emoji = _team_to_emoji(team)
    opponent_emoji = _team_to_emoji("RED") if team == "BLUE" else _team_to_emoji("BLUE")
    remaining = remaining_words_for_team(state, team)
    board_words = set(game.state.board.all_words)

    user_msg = SPYMASTER_USER_PROMPT.format(
        team=team,
        team_emoji=team_emoji,
        opponent_emoji=opponent_emoji,
        board=board_str,
        remaining_words=remaining,
    )

    max_attempts = max(1, spymaster.max_iterations)
    for _ in range(max_attempts):
        inc_llm_calls(step=f"{spymaster.name}.run")
        result, assistant_msg, _, _ = spymaster.run(
            user_message=user_msg, message_history=message_history
        )
        private_reasoning = (
            result.get("reasoning") or (assistant_msg.get("reasoning_content") or "")
        ).strip()
        visible = (assistant_msg.get("content") or "").strip()
        combined_parts = []
        if private_reasoning:
            combined_parts.append(f"[PRIVATE REASONING]\n{private_reasoning}")
        if visible:
            combined_parts.append(visible)
        combined_message = "\n\n".join(combined_parts)
        if combined_message:
            message_history.append(
                {"role": "assistant", "content": f"SPYMASTER: {combined_message}"}
            )
            
            actor = LLMActor(name=spymaster.name, model=spymaster.model)
            spymaster_event = SpymasterEvent(
                team_color=state.current_turn.team,
                player_role=PlayerRole.HINTER,
                actor=actor,
                reasoning=private_reasoning,
            )
            game.state.history.add_event(spymaster_event)
        if result.get("type") != "hint":
            return False, {"reason": f"unexpected result: {result}"}
        

        clue_raw = result.get("clue") or ""
        clue = clue_raw.strip()
        qty = int(result.get("quantity", 1))

        if canonical_format(clue) in board_words:
            message_history.append(
                {
                    "role": "user",
                    "content": (
                        f"system: hint rejected for {clue.upper()}: "
                        "clue cannot be a card on the board. Choose another word."
                    ),
                }
            )
            continue

        actor = LLMActor(name=spymaster.name, model=spymaster.model)

        try:
            hint_res = game.give_hint(word=clue, card_amount=qty, actor=actor)
        except Exception as e:  # pylint: disable=broad-except
            return False, {
                "reason": f"hint rejected: {e}",
                "clue": clue,
                "quantity": qty,
            }
        if not hint_res.success:
            return False, {
                "reason": hint_res.reason or "hint not applied",
                "clue": clue,
                "quantity": qty,
            }
        return True, {"clue": clue, "quantity": qty}

    return False, {"reason": "hint attempts exhausted"}


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
                f"{agent_name.upper()}: "
                f"{'PASS' if vote.lower() == 'pass' else vote.upper()}"
                for agent_name, vote in votes_by_agent.items()
            )

        # Iterate limited discussion/voting rounds to reach majority
        for round_i in range(max_rounds):
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

                inc_llm_calls(step=f"{agent.name}.run")
                result, assistant_msg, _, _ = agent.run(
                    user_message=user_msg, message_history=message_history
                )

                # Create LLM actor for this operative
                actor = LLMActor(name=agent.name, model=agent.model)

                if result.get("type") == "talk":
                    talk_msg = result.get("message", "")

                    # Add operative event for interpretability
                    operative_event = OperativeEvent(
                        team_color=team_turn,
                        player_role=PlayerRole.GUESSER,
                        actor=actor,
                        tool=OperativeToolType.TALK,
                        message=talk_msg,
                    )
                    game.state.history.add_event(operative_event)

                    message_history.append(
                        {"role": "assistant", "content": f"{agent.name}: {talk_msg}"}
                    )
                    print(f"{agent.name.upper()}: {talk_msg}")
                elif result.get("type") == "vote":
                    word = str(result.get("word", "")).strip()
                    if word:
                        try:
                            card_index = game.state.board.find_card_index(word)
                        except CardNotFoundError:
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"system: vote rejected for {word.upper()}: "
                                        "word not on the board."
                                    ),
                                }
                            )
                            print(
                                f"{agent.name.upper()} attempted invalid vote {word.upper()} (not on board)"
                            )
                            continue
                        card = game.state.board.cards[card_index]
                        if card.revealed:
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"system: vote rejected for {word.upper()}: "
                                        "card already revealed."
                                    ),
                                }
                            )
                            print(
                                f"{agent.name.upper()} attempted invalid vote {word.upper()} (already revealed)"
                            )
                            continue
                        # Add operative event for interpretability
                        operative_event = OperativeEvent(
                            team_color=team_turn,
                            player_role=PlayerRole.GUESSER,
                            actor=actor,
                            tool=OperativeToolType.VOTE_GUESS,
                            message=word,
                        )
                        game.state.history.add_event(operative_event)

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
                        if changed:
                            print(
                                f"{agent.name.upper()} changes vote to {word.upper()}"
                            )
                        elif reaffirmed:
                            print(
                                f"{agent.name.upper()} reaffirms vote for {word.upper()}"
                            )
                        else:
                            print(f"{agent.name.upper()} votes for {word.upper()}")
                elif result.get("type") == "pass":
                    # Add operative event for interpretability
                    operative_event = OperativeEvent(
                        team_color=team_turn,
                        player_role=PlayerRole.GUESSER,
                        actor=actor,
                        tool=OperativeToolType.VOTE_PASS,
                        message=None,
                    )
                    game.state.history.add_event(operative_event)

                    # Treat 'pass' as a vote option; require majority like word guesses
                    previous_vote = votes_by_agent.get(agent.name)
                    votes_by_agent[agent.name] = "pass"
                    changed = (
                        previous_vote is not None and previous_vote.lower() != "pass"
                    )
                    reaffirmed = (
                        previous_vote is not None and previous_vote.lower() == "pass"
                    )
                    if changed:
                        print(f"{agent.name.upper()} changes vote to PASS")
                    elif reaffirmed:
                        print(f"{agent.name.upper()} reaffirms vote to PASS")
                    else:
                        print(f"{agent.name.upper()} votes to PASS")
                else:
                    # Ignore unknown result types
                    pass

                # Check majority after each action
                majority = collect_majority_vote(
                    list(votes_by_agent.values()), quorum=len(ops)
                )
                if majority:
                    # Create LLM actor representing the team consensus
                    # Use first operative as representative
                    actor = LLMActor(
                        name=f"{_name(team_turn)}-team", model=ops[0].model
                    )

                    if majority == "pass":
                        # Majority agrees to pass
                        vote_summary = formatted_votes()
                        try:
                            _ = game.pass_turn(actor=actor)
                        except Exception as e:  # pylint: disable=broad-except
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": f"system: pass failed: {e}",
                                }
                            )
                            print(f"Vote result: PASS -> failed ({e})")
                        else:
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": f"system: team decided to PASS; votes={vote_summary}",
                                }
                            )
                            print("Vote result: PASS -> turn passed")
                        votes_by_agent.clear()
                        return
                    else:
                        guess_word = majority
                        vote_summary = formatted_votes()
                        try:
                            guess_res = game.make_guess(word=guess_word, actor=actor)
                        except Exception as e:  # pylint: disable=broad-except
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": f"system: guess '{guess_word}' failed: {e}",
                                }
                            )
                            print(f"Vote result: {guess_word.upper()} -> failed ({e})")
                            return

                        # Log outcome
                        correctness = "correct" if guess_res.correct else "wrong"
                        message_history.append(
                            {
                                "role": "user",
                                "content": f"system: guessed {guess_word.upper()} -> {correctness}; left_guesses={guess_res.left_guesses}",
                            }
                        )
                        print(
                            f"Vote result: {guess_word.upper()} -> {correctness.upper()}"
                        )
                        if vote_summary != "(none)":
                            message_history.append(
                                {
                                    "role": "user",
                                    "content": f"system: vote summary -> {vote_summary}",
                                }
                            )

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
        actor = LLMActor(name=f"{_name(team_turn)}-team", model=ops[0].model)
        try:
            _ = game.pass_turn(actor=actor)
        except Exception as e:  # pylint: disable=broad-except
            message_history.append(
                {"role": "user", "content": f"system: pass failed: {e}"}
            )
            print(f"Vote result: PASS -> failed ({e})")
        else:
            print("Vote result: NO CONSENSUS -> PASS")
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

    round_number = 1

    # Main game loop
    print(f"Starting Codenames game: {game}")
    while not game.is_game_over():
        state = game.get_state(show_colors=False)
        turn = state.current_turn
        team = turn.team
        team_key = _name(team)

        if _name(turn.role) == "HINTER":
            spy = blue_spy if team_key == "BLUE" else red_spy
            team_label = team_key.upper()
            print(f"\n=== ROUND {round_number}: TEAM {team_label} ===")
            print("Board (uncensored):")
            print(format_board_for_spymaster(game))
            ok, info = spymaster_turn(game, spy, spymaster_histories[team_key])
            if not ok:
                print(f"Spymaster error for {team_key}: {info}")
                # If spymaster fails, try to pass turn to avoid deadlock
                try:
                    _ = game.pass_turn()
                except Exception:
                    break
            else:
                print(
                    f"{spy.name.upper()} gives clue: {info['clue'].upper()} {info['quantity']}"
                )
            round_number += 1
        else:
            ops = blue_ops if team_key == "BLUE" else red_ops
            history_before = len(operative_histories[team_key])
            guesser_turn(game, ops, operative_histories[team_key])
            round_messages = operative_histories[team_key][history_before:]
            summary = summarize_round_messages(round_messages, model=model)
            if summary:
                spymaster_histories[team_key].append(
                    {
                        "role": "user",
                        "content": f"OPERATIVE SUMMARY: {summary}",
                    }
                )

        # breakpoint()

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
