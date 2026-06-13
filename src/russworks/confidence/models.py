from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class ConfidenceBreakdown:
    data_completeness: float = 0.0
    sample_size_quality: float = 0.0
    lineup_confirmation: float = 0.0
    integrity_warnings: float = 0.0
    environment_certainty: float = 0.0
    pitch_mix_certainty: float = 0.0
    weak_spot_certainty: float = 0.0
    bullpen_certainty: float = 0.0
    historical_consistency: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class ConfidenceProfile:
    subject: str
    subject_type: str
    breakdown: ConfidenceBreakdown
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceResult:
    subject: str
    subject_type: str
    confidence_score: float
    confidence_grade: str
    confidence_reasoning: list[str] = field(default_factory=list)
    breakdown: ConfidenceBreakdown = field(default_factory=ConfidenceBreakdown)

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
