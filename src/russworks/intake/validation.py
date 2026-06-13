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
    if game.environment is not None:
        _validate_game_team_alignment(game, missing)

    for team in game.teams:
        if team.starting_pitcher is None or not team.starting_pitcher.name:
            missing["pitcher"].append(f"{team.team} starting pitcher")
        elif team.starting_pitcher.team and team.starting_pitcher.team != team.team:
            missing["team_opponent_mismatch"].append(
                f"{team.team} starting pitcher {team.starting_pitcher.name} is assigned to {team.starting_pitcher.team}"
            )
        if not team.batters:
            missing["lineup"].append(f"{team.team} lineup")
            continue
        slot_to_names: Dict[int, List[str]] = defaultdict(list)
        batter_names: Dict[str, List[str]] = defaultdict(list)
        for batter in team.batters:
            label = batter.name or f"{team.team} unnamed batter"
            if not batter.confirmed:
                missing["confirmed_lineup"].append(label)
            if batter.lineup_slot is None:
                missing["lineup_position"].append(label)
            elif not _valid_lineup_slot(batter.lineup_slot):
                missing["invalid_lineup_position"].append(
                    f"{label} lineup slot {batter.lineup_slot} is invalid; expected 1-9"
                )
            else:
                slot_to_names[batter.lineup_slot].append(label)
            if not batter.team:
                missing["batter_team"].append(label)
            elif batter.team != team.team:
                missing["team_opponent_mismatch"].append(
                    f"{label} is listed under {team.team} but has batter team {batter.team}"
                )
            if batter.name:
                batter_names[_normal_key(batter.name)].append(label)

        for slot in range(1, 10):
            if slot not in slot_to_names:
                missing["missing_lineup_slot"].append(f"{team.team} lineup slot {slot}")
        for slot, names in sorted(slot_to_names.items()):
            if len(names) > 1:
                missing["duplicate_lineup_slot"].append(
                    f"{team.team} lineup slot {slot}: {', '.join(names)}"
                )
        for names in batter_names.values():
            if len(names) > 1:
                missing["duplicate_batter"].append(f"{team.team} duplicate batter {names[0]}")

    if not game.weak_spots:
        missing["weak_spot"].append("pitcher weak spot data")
    if not game.hr_matchups:
        missing["hr_matchup"].append("HR matchup data")

    return dict(missing)


def _validate_game_team_alignment(game: GameIntake, missing: Dict[str, List[str]]) -> None:
    assert game.environment is not None
    if game.away_team.team != game.environment.away_team:
        missing["team_opponent_mismatch"].append(
            f"away team intake {game.away_team.team} does not match environment away team {game.environment.away_team}"
        )
    if game.home_team.team != game.environment.home_team:
        missing["team_opponent_mismatch"].append(
            f"home team intake {game.home_team.team} does not match environment home team {game.environment.home_team}"
        )
    if game.away_team.team == game.home_team.team:
        missing["team_opponent_mismatch"].append(f"away and home teams are both {game.away_team.team}")


def _valid_lineup_slot(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 9


def _normal_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _format_missing_data(missing: Dict[str, List[str]]) -> str:
    parts = []
    for category, values in missing.items():
        parts.append(f"{category}: {', '.join(values)}")
    return "Step 2 blocked. Missing required intake data: " + "; ".join(parts)
