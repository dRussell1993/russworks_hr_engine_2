from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class BatterView:
    rank: int
    batter: str
    team: str
    opponent: str
    lineup_slot: int
    russ_score: float
    tier: str
    confidence_score: float
    confidence_grade: str
    key_factors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TeamView:
    rank: int
    team: str
    opponent: str
    tag_grade: str
    cps_grade: str
    total_cluster_score: float
    cluster_strength_label: str
    cluster_captain: str = ""
    hidden_cluster_beneficiary: str = ""
    confidence_grade: str = ""


@dataclass(frozen=True)
class SlipView:
    name: str
    slip_type: str
    confidence_score: float
    confidence_grade: str
    batters: list[str] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    justification: str = ""


@dataclass(frozen=True)
class PortfolioView:
    risk_grade: str = ""
    risk_score: float = 0.0
    team_exposure: dict[str, float] = field(default_factory=dict)
    game_exposure: dict[str, float] = field(default_factory=dict)
    confidence_exposure: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    diversification_recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationView:
    simulation_count: int = 0
    expected_hit_rate: float = 0.0
    expected_roi: float = 0.0
    expected_variance: float = 0.0
    drawdown_risk: float = 0.0
    portfolio_volatility: float = 0.0
    risk_grade: str = ""
    confidence_intervals: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class SchedulerView:
    generated_at: str = ""
    success: bool = True
    task_status_counts: dict[str, int] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardView:
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    batters: list[BatterView] = field(default_factory=list)
    teams: list[TeamView] = field(default_factory=list)
    slips: list[SlipView] = field(default_factory=list)
    portfolio: PortfolioView = field(default_factory=PortfolioView)
    simulation: SimulationView = field(default_factory=SimulationView)
    scheduler: SchedulerView = field(default_factory=SchedulerView)
    provider_health: list[dict[str, Any]] = field(default_factory=list)
    confidence_views: dict[str, Any] = field(default_factory=dict)
    explanations: dict[str, Any] = field(default_factory=dict)
    command_center: dict[str, Any] = field(default_factory=dict)
    dashboard_summary: dict[str, Any] = field(default_factory=dict)
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
