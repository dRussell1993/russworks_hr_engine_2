from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class RiskTarget(str, Enum):
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"


@dataclass(frozen=True)
class DiversificationRecommendation:
    category: str
    target: RiskTarget
    message: str
    suggested_swaps: list[str] = field(default_factory=list)
    exposure_reduction_opportunities: list[str] = field(default_factory=list)
    diversified_alternatives: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiversificationProfile:
    target: RiskTarget = RiskTarget.BALANCED
    team_threshold: float = 0.40
    game_threshold: float = 0.50
    cluster_threshold: float = 0.35
    confidence_threshold: float = 0.30
    archetype_threshold: float = 0.45


@dataclass(frozen=True)
class DiversificationResult:
    generated_at: str
    target: RiskTarget
    recommendations: list[DiversificationRecommendation] = field(default_factory=list)
    suggested_swaps: list[str] = field(default_factory=list)
    exposure_reduction_opportunities: list[str] = field(default_factory=list)
    diversified_portfolio_alternatives: list[str] = field(default_factory=list)
    concentration_summary: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return True

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
