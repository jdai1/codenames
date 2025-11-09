#!/usr/bin/env python3
"""
Calculate TrueSkill ratings for models based on game results from log files.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple
import trueskill


def load_log_files(log_dir: str = "logs") -> List[Dict]:
    """Load all JSON log files from the logs directory."""
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"Error: Log directory '{log_dir}' not found")
        return []

    results = []
    for log_file in sorted(log_path.glob("*.json")):
        try:
            with open(log_file, "r") as f:
                data = json.load(f)
                results.append(data)
        except Exception as e:
            print(f"Warning: Failed to load {log_file}: {e}")

    return results


def extract_match_results(logs: List[Dict]) -> List[Tuple[str, str]]:
    """
    Extract match results from logs.
    Returns list of (winner_model, loser_model) tuples.
    """
    matches = []

    for log in logs:
        if "winner" not in log or "models" not in log:
            continue

        winner_team = log["winner"]
        models = log["models"]

        winner_model = models.get(winner_team)
        loser_team = "RED" if winner_team == "BLUE" else "BLUE"
        loser_model = models.get(loser_team)

        if winner_model and loser_model:
            matches.append((winner_model, loser_model))

    return matches


def calculate_trueskill_ratings(
    matches: List[Tuple[str, str]],
) -> Dict[str, trueskill.Rating]:
    """
    Calculate TrueSkill ratings for all models based on match results.
    Returns a dictionary mapping model names to their TrueSkill ratings.
    """
    # Initialize ratings for all models
    ratings: Dict[str, trueskill.Rating] = {}

    # Get all unique models
    all_models = set()
    for winner, loser in matches:
        all_models.add(winner)
        all_models.add(loser)

    # Initialize all models with default TrueSkill rating
    for model in all_models:
        ratings[model] = trueskill.Rating()

    # Process each match
    for winner_model, loser_model in matches:
        winner_rating = ratings[winner_model]
        loser_rating = ratings[loser_model]

        # Update ratings based on match result
        # TrueSkill: winner beats loser (rank 0 beats rank 1)
        winner_rating, loser_rating = trueskill.rate_1vs1(winner_rating, loser_rating)

        ratings[winner_model] = winner_rating
        ratings[loser_model] = loser_rating

    return ratings


def get_rankings(
    ratings: Dict[str, trueskill.Rating],
) -> List[Tuple[str, float, float]]:
    """
    Get sorted rankings with model name, mean skill, and confidence interval.
    Returns list of (model_name, mean_skill, confidence) tuples, sorted by mean skill.
    Ratings are multiplied by 10 for readability.
    """
    rankings = []

    for model, rating in ratings.items():
        # TrueSkill rating has mu (mean) and sigma (uncertainty)
        mean_skill = rating.mu * 100
        confidence = rating.sigma * 100  # Conservative estimate
        rankings.append((model, mean_skill, confidence))

    # Sort by mean skill (descending)
    rankings.sort(key=lambda x: x[1], reverse=True)
    return rankings


def print_rankings(rankings: List[Tuple[str, float, float]]):
    """Print rankings in a formatted table."""
    print("\n" + "=" * 80)
    print("TrueSkill Rankings")
    print("=" * 80)
    print(f"{'Rank':<6} {'Model':<40} {'Rating':<15} {'Standard Deviation':<15}")
    print("-" * 80)

    for rank, (model, mean_skill, confidence) in enumerate(rankings, 1):
        print(f"{rank:<6} {model:<40} {mean_skill:>14.2f} {confidence:>14.2f}")

    print("=" * 80)
    print(f"\nTotal models ranked: {len(rankings)}")
    print("\nNote: Ratings are TrueSkill values multiplied by 100. ")


def main():
    """Main function to load logs, calculate ratings, and display rankings."""
    # Load all log files
    print("Loading log files...")
    logs = load_log_files("logs")

    if not logs:
        print("No log files found or failed to load any logs.")
        return

    print(f"Loaded {len(logs)} log file(s)")

    # Extract match results
    print("Extracting match results...")
    matches = extract_match_results(logs)

    if not matches:
        print("No valid match results found in logs.")
        return

    print(f"Found {len(matches)} match(es)")

    # Calculate TrueSkill ratings
    print("Calculating TrueSkill ratings...")
    ratings = calculate_trueskill_ratings(matches)

    # Get and display rankings
    rankings = get_rankings(ratings)
    print_rankings(rankings)

    # Optionally save to file
    output_file = "rankings.json"
    output_data = {
        "rankings": [
            {
                "rank": rank,
                "model": model,
                "mean_skill": float(mean_skill),
                "standard_deviation": float(confidence),
            }
            for rank, (model, mean_skill, confidence) in enumerate(rankings, 1)
        ],
        "total_matches": len(matches),
        "total_models": len(ratings),
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nRankings saved to {output_file}")


if __name__ == "__main__":
    main()
