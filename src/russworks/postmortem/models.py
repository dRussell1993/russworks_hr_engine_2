from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ActualHomeRunEntry:
    team: str
    batter: str
    pitch: str
    pitcher: str
    inning: int
    exit_velocity: float
    distance: float
    angle: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WinnerLogEntry:
    team: str
    batter: str
    pitch: str
    pitcher: str
    inning: int
    exit_velocity: float
    distance: float
    angle: float
    slip_names: List[str] = field(default_factory=list)
    slip_types: List[str] = field(default_factory=list)
    archetypes: List[str] = field(default_factory=list)
    source: str = "missed_by_step5"


@dataclass(frozen=True)
class LoserLogEntry:
    team: str
    batter: str
    slip_name: str
    slip_type: str
    tag: str
    cps: str
    russ_score: float
    slip_role: str
    archetypes: List[str] = field(default_factory=list)
    reason: str = "Step 5 leg did not hit actual HR list."


@dataclass(frozen=True)
class FalsePositiveEntry:
    team: str
    batter: str
    slip_name: str
    slip_type: str
    reason: str
    overweighted_modules: List[str] = field(default_factory=list)
    suggested_adjustment: str = "Review thresholds; do not auto-change weights."


@dataclass(frozen=True)
class AdjustmentLogEntry:
    module: str
    direction: str
    reason: str
    evidence_count: int
    recommendation: str


@dataclass(frozen=True)
class CalibrationRecommendation:
    module: str
    action: str
    suggested_delta: float
    confidence: str
    rationale: str
    supporting_archetypes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PostMortemReport:
    actual_home_runs: List[ActualHomeRunEntry] = field(default_factory=list)
    winner_log: List[WinnerLogEntry] = field(default_factory=list)
    loser_log: List[LoserLogEntry] = field(default_factory=list)
    false_positive_log: List[FalsePositiveEntry] = field(default_factory=list)
    adjustment_log: List[AdjustmentLogEntry] = field(default_factory=list)
    calibration_recommendations: List[CalibrationRecommendation] = field(default_factory=list)
    explanation_summaries: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors
