from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class SimulationRiskGrade(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class SimulationScenario:
    simulation_count: int = 1000
    stake_per_slip: float = 1.0
    payout_multiplier: float = 10.0
    historical_hit_rate: float | None = None
    random_seed: int = 34


@dataclass(frozen=True)
class PortfolioSimulation:
    slip_name: str
    slip_type: str
    legs: int
    hit_probability: float
    average_russ_score: float
    average_confidence_score: float
    team_exposure: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SimulationSummary:
    simulation_count: int
    expected_hit_rate: float
    expected_roi: float
    expected_variance: float
    drawdown_risk: float
    portfolio_volatility: float
    confidence_intervals: dict[str, dict[str, float]] = field(default_factory=dict)
    risk_grade: SimulationRiskGrade = SimulationRiskGrade.LOW


@dataclass(frozen=True)
class SimulationResult:
    generated_at: str
    scenario: SimulationScenario
    portfolio_simulations: list[PortfolioSimulation] = field(default_factory=list)
    summary: SimulationSummary | None = None
    portfolio_exposure: dict[str, dict[str, float]] = field(default_factory=dict)
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
