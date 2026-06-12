from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class LineupSlotTrendInput:
    lineup_slot: int
    tag_grade: str = "B"
    cps_grade: str = "B"
    has_strong_pvs: bool = False
    has_environment_boost: bool = False


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
    baselines = {
        1: 10.0,
        2: 5.0,
        3: 12.0,
        4: 15.0,
        5: 7.0,
        6: 0.0,
        7: -2.0,
        8: -6.0,
        9: -8.0,
    }
    score = baselines.get(input_data.lineup_slot, -8.0)
    notes: List[str] = []

    if input_data.lineup_slot == 7 and _is_a_level(input_data.tag_grade) and _is_a_level(input_data.cps_grade):
        score = 8.0
        notes.append("slot 7 cluster override")

    if input_data.lineup_slot in {8, 9} and input_data.has_strong_pvs:
        score += 3.0
        notes.append("lower-lineup PVS relief")
    if input_data.lineup_slot in {8, 9} and input_data.has_environment_boost:
        score += 2.0
        notes.append("lower-lineup environment relief")

    multiplier = round(1.0 + (score / 100.0), 3)
    return LineupSlotTrendMultiplier(
        slot=input_data.lineup_slot,
        score=round(score, 2),
        multiplier=multiplier,
        label=_label(score),
        notes=notes,
    )
