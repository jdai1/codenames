#!/usr/bin/env python3
"""Simple CLI for Codenames game."""

from engine.game_main import CodenamesGame


def print_board(game, show_colors=False):
    """Print the current board state."""
    print(game.state.board.printable_string if show_colors else game.state.board.censored.printable_string)


def print_score(game):
    """Print the current score."""
    score = game.get_score()
    print(
        f"Score - Blue: {score.blue.revealed}/{score.blue.total} | "
        f"Red: {score.red.revealed}/{score.red.total}"
    )
    print()


def print_event_history(game):
    """Print the event history for both teams."""
    history = game.state.history

    print("\n" + "=" * 50)
    print("EVENT HISTORY")
    print("=" * 50)

    # Print Blue Team History
    print("\n🟦 BLUE TEAM HISTORY:")
    print("-" * 50)
    blue_history = history.blue_team

    if blue_history.all_events:
        for event in blue_history.all_events:
            print(f"  {event}")
    else:
        print("  No events recorded")

    print(f"\nSummary:")
    print(f"  Hints given: {len(blue_history.hints_given)}")
    print(f"  Guesses made: {len(blue_history.guesses_made)}")
    print(f"  Chat messages: {len(blue_history.chat_messages)}")
    print(f"  Passes: {len(blue_history.passes)}")

    # Print Red Team History
    print("\n🟥 RED TEAM HISTORY:")
    print("-" * 50)
    red_history = history.red_team

    if red_history.all_events:
        for event in red_history.all_events:
            print(f"  {event}")
    else:
        print("  No events recorded")

    print(f"\nSummary:")
    print(f"  Hints given: {len(red_history.hints_given)}")
    print(f"  Guesses made: {len(red_history.guesses_made)}")
    print(f"  Chat messages: {len(red_history.chat_messages)}")
    print(f"  Passes: {len(red_history.passes)}")

    # Print Global Timeline
    print("\n🌍 GLOBAL TIMELINE:")
    print("-" * 50)
    if history.global_events:
        for event in history.global_events:
            print(f"  {event}")
    else:
        print("  No events recorded")

    print()


def get_hint():
    """Get a hint from the spymaster."""
    print("Enter your hint:")
    word = input("  Word: ").strip()
    try:
        count = int(input("  Number of cards: ").strip())
        return word, count
    except ValueError:
        print("Invalid number. Try again.")
        return get_hint()


def get_guess(game):
    """Get a guess from the operative."""
    turn = game.get_current_turn()
    print(f"Guesses remaining: {turn.left_guesses}")
    print("Enter word to guess (or 'pass' to end turn):")

    guess_input = input("  > ").strip()

    if guess_input.lower() == "pass":
        return None

    return guess_input


def main():
    """Run the Codenames CLI game."""
    print("=" * 50)
    print("CODENAMES CLI")
    print("=" * 50)
    print()

    # Create a new game
    game = CodenamesGame(language="english", board_size=25)

    print("Game started!")
    print_score(game)

    # Game loop
    while not game.is_game_over():
        turn = game.get_current_turn()

        print("-" * 50)
        print(f"{turn.team} Team - {turn.role}")
        print("-" * 50)
        print()

        if turn.role == "HINTER":
            # Spymaster's turn
            print_board(game, show_colors=True)
            print_score(game)

            word, count = get_hint()
            try:
                result = game.give_hint(word, count)
                print(f"\n✓ Hint given: {result.hint.word} {result.hint.card_amount}")
                print(f"  Guesses available: {result.left_guesses}")
            except ValueError as e:
                print(f"\n✗ Error: {e}")
                print("Try again.")

        else:
            # Operative's turn
            print_board(game, show_colors=False)
            print_score(game)

            last_hint = game.get_last_hint()
            if last_hint:
                print(f"Current hint: {last_hint.word} {last_hint.card_amount}")
            print()

            while game.get_current_turn().left_guesses > 0 and not game.is_game_over():
                guess_word = get_guess(game)

                if guess_word is None:
                    # Pass
                    result = game.pass_turn()
                    print(f"\n✓ Passed turn. Next team: {result.next_team}")
                    break

                try:
                    result = game.make_guess(guess_word)

                    if result.success:
                        card = result.guessed_card
                        correct_marker = (
                            "✓ Correct!" if result.correct else "✗ Wrong team!"
                        )
                        print(f"\nRevealed: {card.word} - {card.color}")
                        print(f"Result: {correct_marker}")
                        print_board(game, show_colors=False)
                        print_score(game)

                        if result.is_game_over:
                            break

                        if not result.correct:
                            print("Turn ended.")
                            break
                except ValueError as e:
                    print(f"\n✗ Error: {e}")
                    print("Try again.")
        # Print event history
        print_event_history(game)

    # Game over
    print("\n" + "=" * 50)
    print("GAME OVER!")
    print("=" * 50)

    winner = game.get_winner()
    if winner:
        print(f"Winner: {winner.team_color} team")
        print(f"Reason: {winner.reason}")

    print()
    print_board(game, show_colors=True)
    print_score(game)


if __name__ == "__main__":
    main()
