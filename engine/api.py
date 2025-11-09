#!/usr/bin/env python3
"""Flask API server for Codenames game."""

import json
import random
from typing import Dict

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS

from engine.game_main import CodenamesGame
from engine.game.events import UserActor
from engine.game.player import PlayerRole
from run_agents import (
    build_operatives,
    build_spymaster,
    spymaster_turn,
    guesser_turn,
    _name,
)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# In-memory storage for games
games: Dict[str, CodenamesGame] = {}


@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify(
        {"name": "Codenames API", "version": "1.0.0", "active_games": len(games)}
    )


@app.route("/games", methods=["POST"])
def create_game():
    """
    Create a new game.

    Body (optional):
        {
            "language": "english",
            "board_size": 25,
            "seed": null
        }
    """

    data = request.get_json() or {}

    language = data.get("language", "english")
    board_size = data.get("board_size", 25)
    seed = data.get("seed")
    if seed is None:
        seed = random.randint(0, 1_000_000_000)

    try:
        game = CodenamesGame(language=language, board_size=board_size, seed=seed)
        games[game.game_id] = game

        state = game.get_state(show_colors=True)

        return jsonify(
            {
                "game_id": game.game_id,
                "message": "Game created successfully",
                "game_state": state.dict(),
            }
        ), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# Add hint history
@app.route("/games/<game_id>", methods=["GET"])
def get_game_state(game_id: str):
    """
    Get full game state.

    Query params:
        show_colors: true/false (default: false) - show all card colors
        include_history: true/false (default: false) - include event history
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    show_colors = request.args.get("show_colors", "false").lower() == "true"

    state = game.get_state(show_colors=show_colors, include_history=True)
    return jsonify(state.dict())


@app.route("/games/<game_id>/hint", methods=["POST"])
def give_hint(game_id: str):
    """
    Give a hint (Spymaster action).

    Body:
        {
            "word": "ocean",
            "card_amount": 2
        }
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    data = request.get_json()

    if not data or "word" not in data or "card_amount" not in data:
        return jsonify({"error": "Missing required fields: word, card_amount"}), 400

    # Create actor for human player
    actor = UserActor(name="Human Player")

    try:
        result = game.give_hint(data["word"], data["card_amount"], actor=actor)
        return jsonify(result.dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/games/<game_id>/guess", methods=["POST"])
def make_guess(game_id: str):
    """
    Make a guess (Operative action).

    Body:
        {
            "word": "ocean"
        }
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    data = request.get_json()

    if not data or "word" not in data:
        return jsonify({"error": "Missing required field: word"}), 400

    # Create actor for human player
    actor = UserActor(name="Human Player")

    try:
        result = game.make_guess(data["word"], actor=actor)
        return jsonify(result.dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/games/<game_id>/pass", methods=["POST"])
def pass_turn(game_id: str):
    """Pass the turn (Operative action)."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]

    # Create actor for human player
    actor = UserActor(name="Human Player")

    try:
        result = game.pass_turn(actor=actor)
        return jsonify(result.dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/games/<game_id>/ai/hint", methods=["POST"])
def ai_give_hint(game_id: str):
    """
    AI generates and gives a hint (Spymaster action).

    Body: {"model": "gpt-4"} (optional, default: gpt-4)

    Response: HintResult or error
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    data = request.get_json() or {}
    model = data.get("model", "gpt-4")

    try:
        # Build spymaster agent using the same primitive as run_agents.py
        state = game.get_state(show_colors=True)
        team = state.current_turn.team
        spymaster = build_spymaster(team_name=_name(team), model=model)

        # Get message history from game state
        message_history = game.state.get_message_history(
            team, game.state.current_player_role
        )

        # Use the high-level spymaster_turn function from run_agents.py
        success, result_info = spymaster_turn(game, spymaster, message_history)

        if not success:
            return jsonify({"error": result_info.get("reason", "Hint failed")}), 400

        # Return success response with hint details
        return jsonify(
            {
                "success": True,
                "hint": {
                    "word": result_info["clue"],
                    "card_amount": result_info["quantity"],
                    "team_color": _name(team),
                },
                "left_guesses": game.state.left_guesses,
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


@app.route("/games/<game_id>/ai/guess", methods=["POST"])
def ai_make_guess(game_id: str):
    """
    AI generates and makes a guess (Operative action).

    Body: {"model": "gpt-4", "n_operatives": 1} (optional, defaults)

    Response: Server-Sent Events stream of operative events
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    data = request.get_json() or {}
    model = data.get("model", "gpt-4")
    n_operatives = data.get("n_operatives", 1)

    try:
        if game.state.current_player_role != PlayerRole.GUESSER:
            turn = game.state.current_player_role.value
            team_color = _name(game.state.current_team_color)
            return jsonify(
                {
                    "error": "It is not currently the guesser's turn",
                    "current_turn": {
                        "team": team_color,
                        "role": turn,
                    },
                }
            ), 400
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

    def generate():
        """Generate SSE stream of operative events."""
        try:
            # Build operative agents using the same primitive as run_agents.py
            state = game.get_state(show_colors=False)
            team = state.current_turn.team
            operatives = build_operatives(
                team_name=_name(team), model=model, n=n_operatives
            )

            # Get message history from game state
            message_history = game.state.get_message_history(
                team, game.state.current_player_role
            )

            # Use the high-level guesser_turn function from run_agents.py
            # This handles the full guessing logic including voting, multiple guesses, etc.
            # It now yields events as they happen
            for item in guesser_turn(game, operatives, message_history, max_rounds=25):
                # Skip tuples (model_cost, token_usage) - only stream OperativeEvent objects
                if isinstance(item, tuple):
                    continue

                # Send event as SSE - convert datetime to string for JSON serialization
                event_dict = item.dict()
                if 'timestamp' in event_dict and event_dict['timestamp']:
                    event_dict['timestamp'] = event_dict['timestamp'].isoformat()
                yield "data: " + json.dumps(event_dict) + "\n\n"

            # Send final completion event
            yield "data: " + json.dumps({
                "type": "complete",
                "current_turn": {
                    "team": _name(game.state.current_team_color),
                    "role": game.state.current_player_role.value,
                },
                "is_game_over": game.is_game_over(),
            }) + "\n\n"

        except ValueError as e:
            yield "data: " + json.dumps({"type": "error", "error": str(e)}) + "\n\n"
        except Exception as e:  
            yield "data: " + json.dumps({"type": "error", "error": f"Internal error: {str(e)}"}) + "\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
