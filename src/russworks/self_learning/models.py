from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class LearningRecommendationType(str, Enum):
    WEIGHT_REVIEW = "Weight review"
    THRESHOLD_REVIEW = "Threshold review"
    VALIDATION_REVIEW = "Validation review"
    DATA_QUALITY_REVIEW = "Data quality review"
    PORTFOLIO_REVIEW = "Portfolio review"
    DIVERSIFICATION_REVIEW = "Diversification review"


@dataclass(frozen=True)
class LearningObservation:
    source: str
    subject: str
    metric: str
    value: float | int | str
    confidence: float
    summary: str


@dataclass(frozen=True)
class LearningInsight:
    category: str
    subject: str
    summary: str
    confidence: float
    supporting_observations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LearningRecommendation:
    recommendation_type: LearningRecommendationType
    subject: str
    action: str
    confidence: float
    reasoning: str
    supporting_insights: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LearningSummary:
    top_performing_modules: list[str] = field(default_factory=list)
    underperforming_modules: list[str] = field(default_factory=list)
    consistent_strengths: list[str] = field(default_factory=list)
    consistent_weaknesses: list[str] = field(default_factory=list)
    emerging_trends: list[str] = field(default_factory=list)
    confidence_ranked_recommendations: list[LearningRecommendation] = field(default_factory=list)


@dataclass(frozen=True)
class SelfLearningReport:
    generated_at: str
    observations: list[LearningObservation] = field(default_factory=list)
    insights: list[LearningInsight] = field(default_factory=list)
    recommendations: list[LearningRecommendation] = field(default_factory=list)
    summary: LearningSummary = field(default_factory=LearningSummary)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
