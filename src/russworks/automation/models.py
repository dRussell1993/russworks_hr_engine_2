from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any

from russworks.calibration import CalibrationResult
from russworks.dashboard import CalibrationDashboard
from russworks.postmortem import PostMortemReport
from russworks.recommendations import RecommendationReport


@dataclass(frozen=True)
class DailyPostMortemRun:
    date: str
    actual_hr_path: str = ""
    report_path: str = ""
    postmortem_output_dir: str = "data/postmortem"
    dashboard_output_dir: str = "data/dashboard"
    recommendations_output_dir: str = "data/recommendations"
    force: bool = False


@dataclass(frozen=True)
class PostMortemRunResult:
    run: DailyPostMortemRun
    success: bool
    skipped: bool = False
    duplicate: bool = False
    actual_home_runs_loaded: int = 0
    postmortem_report_path: str = ""
    calibration_report_path: str = ""
    dashboard_path: str = ""
    recommendations_path: str = ""
    metadata_path: str = ""
    postmortem_report: PostMortemReport | None = None
    calibration_result: CalibrationResult | None = None
    dashboard: CalibrationDashboard | None = None
    recommendations: RecommendationReport | None = None
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
