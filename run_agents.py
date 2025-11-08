import os
import json
from typing import List, Dict

from agents.operative import OperativeAgent, VoteTool, TalkTool
from agents.prompts import OPERATIVE_SYSTEM_PROMPT, OPERATIVE_USER_PROMPT


def main():
    # Configure model via env or default to a common OpenAI model
    model = os.environ.get("MODEL", "gpt-4o-mini")

    # Simple demo board state
    board = [
        "APPLE",
        "PYRAMID",
        "RIVER",
        "CODE",
        "MARS",
        "PITCH",
        "ORANGE",
        "TABLE",
        "PIANO",
    ]
    clue = "fruit 2"
    number = 2
    votes = []

    user_message = OPERATIVE_USER_PROMPT.format(
        board=", ".join(board), clue=clue, number=number, votes=", ".join(votes)
    )

    # History can include previous assistant/tool messages if desired
    message_history: List[Dict[str, str]] = []

    # Instantiate an operative agent; tools default to Vote/Talk
    agent = OperativeAgent(
        name="operative-1",
        system_prompt=OPERATIVE_SYSTEM_PROMPT,
        tools=[VoteTool(), TalkTool()],
        model=model,
        max_iterations=5,
    )

    result = agent.run(user_message=user_message, message_history=message_history)

    print("Agent result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

