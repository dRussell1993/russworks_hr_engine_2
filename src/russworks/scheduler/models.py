from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class TaskKind(str, Enum):
    PRE_SLATE_RUN = "pre_slate_run"
    MIDDAY_REFRESH = "midday_refresh"
    LINEUP_CONFIRMATION_REFRESH = "lineup_confirmation_refresh"
    END_OF_DAY_POSTMORTEM = "end_of_day_postmortem"
    DASHBOARD_REFRESH = "dashboard_refresh"
    RECOMMENDATION_REFRESH = "recommendation_refresh"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    kind: TaskKind
    run_time_utc: str
    enabled: bool = True
    retry_limit: int = 2
    retry_delay_minutes: int = 15
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskResult:
    task: ScheduledTask
    status: TaskStatus
    started_at: str
    finished_at: str = ""
    last_run: str = ""
    next_run: str = ""
    failures: int = 0
    retries: int = 0
    output_path: str = ""
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SchedulerStatus:
    generated_at: str
    date: str
    tasks: list[TaskResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and all(task.status != TaskStatus.FAILED for task in self.tasks)

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
