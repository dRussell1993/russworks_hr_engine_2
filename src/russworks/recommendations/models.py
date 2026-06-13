from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class WeightRecommendation:
    current_weight: float
    suggested_weight: float
    delta: float
    confidence: str
    trend_direction: str
    applied: bool = False


@dataclass(frozen=True)
class ModuleRecommendation:
    module: str
    current_weight: float
    suggested_weight: float
    confidence: str
    trend_direction: str
    supporting_metrics: dict[str, int | float | str] = field(default_factory=dict)
    reasoning: str = ""
    recommendation: WeightRecommendation | None = None


@dataclass(frozen=True)
class RecommendationReport:
    generated_at: str
    modules: list[ModuleRecommendation] = field(default_factory=list)
    rejected_modules: list[ModuleRecommendation] = field(default_factory=list)
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
