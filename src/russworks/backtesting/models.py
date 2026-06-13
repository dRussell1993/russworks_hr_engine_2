from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any

from russworks.postmortem import CalibrationRecommendation


@dataclass(frozen=True)
class BacktestRequest:
    start_date: str
    end_date: str
    data_root: str = "data/historical"
    actual_hr_data_root: str = "data/postmortem"


@dataclass(frozen=True)
class BacktestSummary:
    start_date: str
    end_date: str
    dates_tested: int
    total_games: int
    total_batters_reviewed: int
    total_hrs_hit: int
    step3_hits: int
    step4_hits: int
    step5_hits: int
    non_superstar_hits: int
    ypi_hits: int
    veteran_hits: int
    catcher_hits: int
    weak_spot_hits: int
    pitch_mix_hits: int
    step3_hit_rate: float
    step4_hit_rate: float
    step5_hit_rate: float
    non_superstar_hit_rate: float
    ypi_hit_rate: float
    veteran_hit_rate: float
    catcher_hit_rate: float
    weak_spot_hit_rate: float
    pitch_mix_hit_rate: float


@dataclass(frozen=True)
class DailyBacktestSummary:
    date: str
    games_reviewed: int
    total_batters_reviewed: int
    total_hrs_hit: int
    step3_hits: int
    step4_hits: int
    step5_hits: int
    non_superstar_hits: int
    ypi_hits: int
    veteran_hits: int
    catcher_hits: int
    weak_spot_hits: int
    pitch_mix_hits: int
    step3_hit_rate: float
    step4_hit_rate: float
    step5_hit_rate: float
    non_superstar_hit_rate: float
    ypi_hit_rate: float
    veteran_hit_rate: float
    catcher_hit_rate: float
    weak_spot_hit_rate: float
    pitch_mix_hit_rate: float
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BacktestResult:
    request: BacktestRequest
    daily_summaries: list[DailyBacktestSummary] = field(default_factory=list)
    summary: BacktestSummary | None = None
    calibration_recommendations: list[CalibrationRecommendation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and all(not daily.errors for daily in self.daily_summaries)

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
