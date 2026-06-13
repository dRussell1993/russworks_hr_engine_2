from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class CalibrationMetric:
    module: str
    appearances: int
    hits: int
    hit_rate: float
    false_positives: int
    false_negatives: int
    confidence_score: float


@dataclass(frozen=True)
class CalibrationRecommendation:
    module: str
    action: str
    suggested_delta: float
    confidence: str
    rationale: str


@dataclass(frozen=True)
class CalibrationResult:
    metrics: list[CalibrationMetric] = field(default_factory=list)
    strength_rankings: list[CalibrationMetric] = field(default_factory=list)
    weakness_rankings: list[CalibrationMetric] = field(default_factory=list)
    recommended_adjustments: list[CalibrationRecommendation] = field(default_factory=list)
    trend_summaries: list[str] = field(default_factory=list)
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
