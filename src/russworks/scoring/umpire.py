from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..config.weights import ScoringWeights, weight
from ..models import Umpire


@dataclass(frozen=True)
class UmpireScoreInput:
    umpire: Optional[Umpire]
    weights: ScoringWeights = field(default_factory=ScoringWeights.defaults)


@dataclass(frozen=True)
class UmpireScore:
    score: float
    label: str
    components: dict[str, float]
    notes: List[str] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _label(score: float) -> str:
    if score >= 3:
        return "hitter lean"
    if score <= -3:
        return "pitcher lean"
    return "neutral"


def calculate_umpire_score(input_data: UmpireScoreInput) -> UmpireScore:
    umpire = input_data.umpire
    weights = input_data.weights.umpire
    if umpire is None:
        return UmpireScore(score=0.0, label="neutral", components={}, notes=["missing umpire"])

    zone = umpire.zone_type.lower()
    notes: List[str] = []
    zone_component = 0.0
    if "walk" in zone or "generous" in zone or "hitter" in zone:
        zone_component += weight(weights, "hitter_zone_bonus", 2.0)
        notes.append("hitter-friendly zone")
    if "strike" in zone or "strict" in zone or "pitcher" in zone:
        zone_component += weight(weights, "pitcher_zone_penalty", -2.0)
        notes.append("pitcher-friendly zone")
    if "hot" in zone:
        zone_component += weight(weights, "hot_zone_bonus", 1.0)
        notes.append("hot run lean")

    called_strike = _clamp(
        (weight(weights, "called_strike_baseline", 32.0) - umpire.called_strike_rate) / weight(weights, "called_strike_divisor", 1.5),
        weight(weights, "called_strike_min", -2.0),
        weight(weights, "called_strike_max", 2.0),
    )
    accuracy = _clamp(
        (weight(weights, "accuracy_baseline", 93.0) - umpire.accuracy) / weight(weights, "accuracy_divisor", 3.0),
        weight(weights, "accuracy_min", -1.5),
        weight(weights, "accuracy_max", 1.5),
    ) if umpire.accuracy else 0.0
    consistency = _clamp(
        (weight(weights, "consistency_baseline", 90.0) - umpire.consistency) / weight(weights, "consistency_divisor", 10.0),
        weight(weights, "consistency_min", -1.0),
        weight(weights, "consistency_max", 1.0),
    ) if umpire.consistency else 0.0
    run_lean = _clamp(
        umpire.run_lean / weight(weights, "run_lean_divisor", 2.0),
        weight(weights, "run_lean_min", -2.0),
        weight(weights, "run_lean_max", 2.0),
    )

    components = {
        "zone": round(zone_component, 2),
        "called_strike": round(called_strike, 2),
        "accuracy": round(accuracy, 2),
        "consistency": round(consistency, 2),
        "run_lean": round(run_lean, 2),
    }
    score = round(sum(components.values()), 2)
    return UmpireScore(score=score, label=_label(score), components=components, notes=notes)
