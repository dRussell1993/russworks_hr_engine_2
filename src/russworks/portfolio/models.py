from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class RiskGrade(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class ExposureReport:
    total_slips: int
    total_legs: int
    team_exposure: dict[str, float] = field(default_factory=dict)
    game_exposure: dict[str, float] = field(default_factory=dict)
    batter_exposure: dict[str, float] = field(default_factory=dict)
    cluster_exposure: dict[str, float] = field(default_factory=dict)
    confidence_exposure: dict[str, float] = field(default_factory=dict)
    slip_archetype_exposure: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class PortfolioRecommendation:
    category: str
    risk_grade: RiskGrade
    message: str
    affected_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioRiskReport:
    risk_grade: RiskGrade
    risk_score: float
    recommendations: list[PortfolioRecommendation] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class PortfolioProfile:
    generated_at: str
    exposure_report: ExposureReport
    risk_report: PortfolioRiskReport
    recommendations: list[PortfolioRecommendation] = field(default_factory=list)

    @property
    def risk_grade(self) -> RiskGrade:
        return self.risk_report.risk_grade

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
