from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class DailySlateStatus:
    date: str
    games_loaded: int
    batters_loaded: int
    confirmed_lineups: int
    missing_lineups: list[str] = field(default_factory=list)
    provider_health: list[dict[str, Any]] = field(default_factory=list)
    validation_failures: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class FormulaHealthReport:
    current_module_weights: dict[str, Any] = field(default_factory=dict)
    top_performing_modules: list[str] = field(default_factory=list)
    worst_performing_modules: list[str] = field(default_factory=list)
    modules_heating_up: list[str] = field(default_factory=list)
    modules_cooling_off: list[str] = field(default_factory=list)
    optimizer_recommendations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DailyExecutionSummary:
    step2_status: str
    step3_status: str
    step4_status: str
    step5_status: str
    reports_generated: list[str] = field(default_factory=list)
    exports_generated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandCenterReport:
    generated_at: str
    slate_status: DailySlateStatus
    formula_health: FormulaHealthReport
    execution_summary: DailyExecutionSummary
    explanations_path: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and not self.execution_summary.errors

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
