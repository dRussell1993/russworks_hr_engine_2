from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class TrendMetric:
    module: str
    seven_day_trend: float
    fourteen_day_trend: float
    thirty_day_trend: float
    season_trend: float
    classification: str
    sample_size: int
    supporting_metrics: dict[str, int | float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrendSummary:
    generated_at: str
    metrics: list[TrendMetric] = field(default_factory=list)
    heating_up: list[str] = field(default_factory=list)
    stable: list[str] = field(default_factory=list)
    cooling_off: list[str] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
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
