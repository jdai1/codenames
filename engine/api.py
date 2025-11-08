#!/usr/bin/env python3
"""Flask API server for Codenames game."""

import json
import time
from typing import Dict
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from engine.game import CodenamesGame
from engine.schema import ReasoningToken, ReasoningTokenType

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# In-memory storage for games
games: Dict[str, CodenamesGame] = {}


@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "name": "Codenames API",
        "version": "1.0.0",
        "active_games": len(games)
    })


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

    try:
        game = CodenamesGame(language=language, board_size=board_size, seed=seed)
        games[game.game_id] = game

        return jsonify({
            "game_id": game.game_id,
            "message": "Game created successfully"
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# Add hint history
@app.route("/games/<game_id>", methods=["GET"])
def get_game_state(game_id: str):
    """
    Get full game state.

    Query params:
        show_colors: true/false (default: false) - show all card colors
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]
    show_colors = request.args.get("show_colors", "false").lower() == "true"

    state = game.get_state(show_colors=show_colors)
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

    try:
        result = game.give_hint(data["word"], data["card_amount"])
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

    try:
        result = game.make_guess(data["word"])
        return jsonify(result.dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/games/<game_id>/pass", methods=["POST"])
def pass_turn(game_id: str):
    """Pass the turn (Operative action)."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]

    try:
        result = game.pass_turn()
        return jsonify(result.dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/games/<game_id>/ai/hint", methods=["POST"])
def ai_give_hint(game_id: str):
    """
    AI generates and gives a hint (Spymaster action) with streaming.

    Body: {} (optional AI config)

    Response: Server-Sent Events stream of ReasoningToken objects
        ReasoningToken = {
            "type": "give-hint-reasoning" | "give-hint-result" | "error",
            "content": str | HintResult
        }

        Example reasoning token: {"type": "give-hint-reasoning", "content": "Analyzing board..."}
        Example result token: {"type": "give-hint-result", "content": {...HintResult...}}
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]

    def generate():
        # TODO: Replace with actual AI agent function that yields ReasoningTokens
        # For now, simulate reasoning tokens
        token1 = ReasoningToken(type=ReasoningTokenType.GIVE_HINT_REASONING, content="Analyzing board...")
        yield json.dumps(token1.dict()) + "\n\n"
        time.sleep(0.5)

        token2 = ReasoningToken(type=ReasoningTokenType.GIVE_HINT_REASONING, content="Identifying patterns...")
        yield json.dumps(token2.dict()) + "\n\n"
        time.sleep(0.5)

        token3 = ReasoningToken(type=ReasoningTokenType.GIVE_HINT_REASONING, content="Generating hint...")
        yield json.dumps(token3.dict()) + "\n\n"
        time.sleep(0.5)

        # Placeholder: Generate hint
        word = "placeholder"
        card_amount = 2

        # Apply hint to game
        try:
            result = game.give_hint(word, card_amount)
            result_token = ReasoningToken(
                type=ReasoningTokenType.GIVE_HINT_RESULT,
                content=result.dict()
            )
            yield json.dumps(result_token.dict()) + "\n\n"
        except ValueError as e:
            error_token = ReasoningToken(type=ReasoningTokenType.ERROR, content=str(e))
            yield json.dumps(error_token.dict()) + "\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route("/games/<game_id>/ai/guess", methods=["POST"])
def ai_make_guess(game_id: str):
    """
    AI generates and makes a guess (Operative action) with streaming.

    Body: {} (optional AI config)

    Response: Server-Sent Events stream of ReasoningToken objects
        ReasoningToken = {
            "type": "make-guess-reasoning" | "make-guess-result" | "error",
            "content": str | GuessResult
        }

        Example reasoning token: {"type": "make-guess-reasoning", "content": "Evaluating cards..."}
        Example result token: {"type": "make-guess-result", "content": {...GuessResult...}}
    """
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game = games[game_id]

    def generate():
        # TODO: Replace with actual AI agent function that yields ReasoningTokens
        # For now, simulate reasoning tokens
        token1 = ReasoningToken(type=ReasoningTokenType.MAKE_GUESS_REASONING, content="Processing hint...")
        yield f"data: {json.dumps(token1.dict())}\n\n"
        time.sleep(0.5)

        token2 = ReasoningToken(type=ReasoningTokenType.MAKE_GUESS_REASONING, content="Evaluating cards...")
        yield f"data: {json.dumps(token2.dict())}\n\n"
        time.sleep(0.5)

        token3 = ReasoningToken(type=ReasoningTokenType.MAKE_GUESS_REASONING, content="Making decision...")
        yield f"data: {json.dumps(token3.dict())}\n\n"
        time.sleep(0.5)

        # Placeholder: Pick first unrevealed card
        board = game.get_board(show_colors=False)
        unrevealed = [card for card in board if not card.revealed]

        guess_word = unrevealed[0].word if unrevealed else None

        if guess_word:
            # Apply guess to game
            try:
                result = game.make_guess(guess_word)
                result_token = ReasoningToken(
                    type=ReasoningTokenType.MAKE_GUESS_RESULT,
                    content=result.dict()
                )
                yield f"data: {json.dumps(result_token.dict())}\n\n"
            except ValueError as e:
                error_token = ReasoningToken(type=ReasoningTokenType.ERROR, content=str(e))
                yield f"data: {json.dumps(error_token.dict())}\n\n"
        else:
            # Pass if no cards left
            try:
                result = game.pass_turn()
                result_token = ReasoningToken(
                    type=ReasoningTokenType.MAKE_GUESS_RESULT,
                    content=result.dict()
                )
                yield f"data: {json.dumps(result_token.dict())}\n\n"
            except ValueError as e:
                error_token = ReasoningToken(type=ReasoningTokenType.ERROR, content=str(e))
                yield f"data: {json.dumps(error_token.dict())}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
