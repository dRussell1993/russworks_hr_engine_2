from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class RuntimeMode(str, Enum):
    LOCAL = "local"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    mode: str = "csv"
    mlb_stats_base_url: str = ""
    baseball_savant_base_url: str = ""
    weather_base_url: str = ""
    ballpark_base_url: str = ""
    provider_timeout_seconds: float = 10.0
    provider_max_retries: int = 2


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = False
    daily_run_time_utc: str = "15:00"
    timezone: str = "UTC"


@dataclass(frozen=True)
class DeploymentConfig:
    runtime_mode: RuntimeMode = RuntimeMode.LOCAL
    date: str = ""
    data_root: str = "data/daily"
    output_root: str = "data/outputs"
    config_path: str = "config/russworks_config.yaml"
    report_volume: str = "data"
    provider: ProviderRuntimeConfig = field(default_factory=ProviderRuntimeConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class DeploymentValidationResult:
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class RuntimeExecutionResult:
    success: bool
    config: DeploymentConfig
    validation: DeploymentValidationResult
    pipeline_result: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
