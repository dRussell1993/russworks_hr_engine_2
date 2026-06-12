from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .game import GameIntake
from .review_queue import ReviewQueue, build_review_queue


class IntakeValidationError(RuntimeError):
    pass


def validate_step2_intake(game: GameIntake, *, raise_on_error: bool = False) -> ReviewQueue:
    missing = _collect_missing_data(game)
    queue = build_review_queue(game, missing)
    if raise_on_error and not queue.is_valid:
        raise IntakeValidationError(_format_missing_data(missing))
    return queue


def _collect_missing_data(game: GameIntake) -> Dict[str, List[str]]:
    missing: Dict[str, List[str]] = defaultdict(list)

    if game.environment is None:
        missing["environment"].append("game environment")
    if game.umpire is None and (game.environment is None or game.environment.umpire is None):
        missing["umpire"].append("umpire")

    for team in game.teams:
        if team.starting_pitcher is None or not team.starting_pitcher.name:
            missing["pitcher"].append(f"{team.team} starting pitcher")
        if not team.batters:
            missing["lineup"].append(f"{team.team} lineup")
            continue
        for batter in team.batters:
            label = batter.name or f"{team.team} unnamed batter"
            if not batter.confirmed:
                missing["confirmed_lineup"].append(label)
            if batter.lineup_slot is None:
                missing["lineup_position"].append(label)
            if not batter.team:
                missing["batter_team"].append(label)

    if not game.weak_spots:
        missing["weak_spot"].append("pitcher weak spot data")
    if not game.hr_matchups:
        missing["hr_matchup"].append("HR matchup data")

    return dict(missing)


def _format_missing_data(missing: Dict[str, List[str]]) -> str:
    parts = []
    for category, values in missing.items():
        parts.append(f"{category}: {', '.join(values)}")
    return "Step 2 blocked. Missing required intake data: " + "; ".join(parts)
