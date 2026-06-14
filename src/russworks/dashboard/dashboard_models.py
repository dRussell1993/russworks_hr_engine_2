from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class ModulePerformance:
    module: str
    appearances: int
    wins: int
    losses: int
    hit_rate: float
    false_positives: int
    false_negatives: int
    confidence_accuracy: float


@dataclass(frozen=True)
class TrendReport:
    label: str
    start_date: str
    end_date: str
    module_trends: list[ModulePerformance] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArchetypePerformance:
    archetype: str
    appearances: int
    wins: int
    losses: int
    hit_rate: float
    false_positives: int
    confidence_accuracy: float


@dataclass(frozen=True)
class AccuracyBucket:
    label: str
    appearances: int
    hits: int
    misses: int
    hit_rate: float


@dataclass(frozen=True)
class AccuracyReview:
    production_readiness: str = "WARNING"
    production_readiness_status: str = "WARNING"
    calibration_enabled: bool = False
    match_integrity: dict[str, Any] = field(default_factory=dict)
    placeholder_predictions_found: list[dict[str, Any]] = field(default_factory=list)
    hr_events_acquired: int = 0
    winners: int = 0
    misses: int = 0
    false_positives: int = 0
    hit_rate: float = 0.0
    hit_rate_by_russ_tier: list[AccuracyBucket] = field(default_factory=list)
    hit_rate_by_confidence_grade: list[AccuracyBucket] = field(default_factory=list)
    hit_rate_by_team_cluster_grade: list[AccuracyBucket] = field(default_factory=list)
    hit_rate_by_slip_type: list[AccuracyBucket] = field(default_factory=list)
    top_false_positives: list[dict[str, Any]] = field(default_factory=list)
    top_false_negatives: list[dict[str, Any]] = field(default_factory=list)
    best_performing_modules: list[ModulePerformance] = field(default_factory=list)
    worst_performing_modules: list[ModulePerformance] = field(default_factory=list)
    top_calibration_recommendations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalibrationDashboard:
    generated_at: str
    modules: list[ModulePerformance] = field(default_factory=list)
    top_performing_modules: list[ModulePerformance] = field(default_factory=list)
    worst_performing_modules: list[ModulePerformance] = field(default_factory=list)
    thirty_day_trends: TrendReport | None = None
    season_trends: TrendReport | None = None
    archetype_success_rates: list[ArchetypePerformance] = field(default_factory=list)
    trend_summaries: list[str] = field(default_factory=list)
    integrity_summaries: list[str] = field(default_factory=list)
    explanation_summaries: list[str] = field(default_factory=list)
    confidence_summaries: list[str] = field(default_factory=list)
    portfolio_summaries: list[str] = field(default_factory=list)
    diversification_summaries: list[str] = field(default_factory=list)
    simulation_summaries: list[str] = field(default_factory=list)
    self_learning_summaries: list[str] = field(default_factory=list)
    scheduler_summaries: list[str] = field(default_factory=list)
    operations_summary: dict[str, Any] = field(default_factory=dict)
    accuracy_review: AccuracyReview | None = None
    validation_summaries: list[str] = field(default_factory=list)
    skipped_game_summaries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
