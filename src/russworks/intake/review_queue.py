from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .batter import BatterIntake
from .game import GameIntake


@dataclass(frozen=True)
class ReviewQueue:
    total_batters: int
    validated_batters: int
    missing_data: Dict[str, List[str]] = field(default_factory=dict)
    review_required: List[BatterIntake] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(self.missing_data.values())


def build_review_queue(game: GameIntake, missing_data: Dict[str, List[str]] | None = None) -> ReviewQueue:
    missing = missing_data or {}
    review_required = [batter for team in game.teams for batter in team.batters if batter.requires_review]
    validated_batters = sum(1 for batter in review_required if batter.confirmed and batter.lineup_slot is not None)
    return ReviewQueue(
        total_batters=len(review_required),
        validated_batters=validated_batters,
        missing_data=missing,
        review_required=review_required,
    )
