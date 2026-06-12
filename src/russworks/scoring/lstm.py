from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..config.weights import ScoringWeights, weight


@dataclass(frozen=True)
class LineupSlotTrendInput:
    lineup_slot: int
    tag_grade: str = "B"
    cps_grade: str = "B"
    has_strong_pvs: bool = False
    has_environment_boost: bool = False
    weights: ScoringWeights = field(default_factory=ScoringWeights.defaults)


@dataclass(frozen=True)
class LineupSlotTrendMultiplier:
    slot: int
    score: float
    multiplier: float
    label: str
    notes: List[str] = field(default_factory=list)


def _is_a_level(grade: str) -> bool:
    return grade.upper().startswith("A")


def _label(score: float) -> str:
    if score >= 10:
        return "premium"
    if score >= 5:
        return "positive"
    if score <= -5:
        return "penalty"
    return "neutral"


def calculate_lstm(input_data: LineupSlotTrendInput) -> LineupSlotTrendMultiplier:
    weights = input_data.weights.lstm
    score = weight(weights, f"slot_{input_data.lineup_slot}", -8.0)
    notes: List[str] = []

    if input_data.lineup_slot == 7 and _is_a_level(input_data.tag_grade) and _is_a_level(input_data.cps_grade):
        score = weight(weights, "slot_7_cluster_override", 8.0)
        notes.append("slot 7 cluster override")

    if input_data.lineup_slot in {8, 9} and input_data.has_strong_pvs:
        score += weight(weights, "lower_lineup_pvs_relief", 3.0)
        notes.append("lower-lineup PVS relief")
    if input_data.lineup_slot in {8, 9} and input_data.has_environment_boost:
        score += weight(weights, "lower_lineup_environment_relief", 2.0)
        notes.append("lower-lineup environment relief")

    return LineupSlotTrendMultiplier(
        slot=input_data.lineup_slot,
        score=round(score, 2),
        multiplier=round(1.0 + (score / 100.0), 3),
        label=_label(score),
        notes=notes,
    )
