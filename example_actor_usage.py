#!/usr/bin/env python3
"""Example showing how to use the Actor system for event tracking."""

from engine.game_main import CodenamesGame
from engine.game.events import UserActor, LLMActor

# Create a new game
game = CodenamesGame(language="english", board_size=25, seed=42)

# Create actors
human_player = UserActor(name="Alice")
gpt4_agent = LLMActor(name="GPT-4 Spymaster", model="gpt-4")
claude_agent = LLMActor(name="Claude Operative", model="claude-3-opus")

# Example 1: Human gives a hint
print("=== Example 1: Human Hint ===")
hint_result = game.give_hint("animal", 2, actor=human_player)
print(f"Hint given: {hint_result.hint}")

# Example 2: LLM makes a guess
print("\n=== Example 2: LLM Guess ===")
board = game.get_board(show_colors=False)
# Find a word to guess
first_unrevealed = next(card for card in board if not card.revealed)
guess_result = game.make_guess(first_unrevealed.word, actor=claude_agent)
print(f"Guess made: {guess_result.guessed_card.word} - Correct: {guess_result.correct}")

# Example 3: Continue until we need to pass
print("\n=== Example 3: Pass Turn ===")
if not game.is_game_over() and game.state.current_player_role.value == "GUESSER":
    pass_result = game.pass_turn(actor=claude_agent)
    print(f"Pass result: {pass_result.action}")

# Example 4: Record chat message
print("\n=== Example 4: Chat Message ===")
game.state.record_chat_message(
    actor=claude_agent,
    message="I think we should focus on finding the animal-related words first.",
    message_metadata={"reasoning": "Strategic analysis based on hint"}
)

# Example 5: View event history
print("\n=== Event History ===")
history = game.state.history

print(f"\nBlue Team Events: {len(history.blue_team.all_events)}")
for event in history.blue_team.all_events:
    print(f"  - {event}")

print(f"\nRed Team Events: {len(history.red_team.all_events)}")
for event in history.red_team.all_events:
    print(f"  - {event}")

print(f"\nGlobal Timeline: {len(history.global_events)} total events")
for event in history.global_events:
    print(f"  - {event}")

# Example 6: Get chat history for a team
print("\n=== Chat History ===")
blue_chats = history.get_chat_history_for_team(game.state.current_team_color)
print(f"Chat messages for current team: {len(blue_chats)}")
for chat in blue_chats:
    print(f"  - {chat}")
