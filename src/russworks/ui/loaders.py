from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DashboardData:
    dashboard_data: dict[str, Any] = field(default_factory=dict)
    operator_report: str = ""
    command_center: dict[str, Any] = field(default_factory=dict)
    calibration_dashboard: dict[str, Any] = field(default_factory=dict)
    full_report: dict[str, Any] = field(default_factory=dict)
    selected_date: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    missing_files: list[str] = field(default_factory=list)


def load_dashboard_outputs(
    *,
    date: str | None = None,
    data_root: str | Path = "data",
) -> DashboardData:
    root = Path(data_root)
    selected_date = date or latest_output_date(root) or ""
    paths = {
        "dashboard_data": str(root / "web" / "dashboard_data.json"),
        "operator_report": str(root / "outputs" / selected_date / "russworks_operator_report.md") if selected_date else "",
        "command_center": str(root / "command_center" / "command_center.json"),
        "calibration_dashboard": str(root / "dashboard" / "dashboard.json"),
        "full_report": str(root / "outputs" / selected_date / "russworks_full_report.json") if selected_date else "",
    }
    missing = [name for name, path in paths.items() if path and not Path(path).exists()]
    return DashboardData(
        dashboard_data=_read_json(paths["dashboard_data"]),
        operator_report=_read_text(paths["operator_report"]),
        command_center=_read_json(paths["command_center"]),
        calibration_dashboard=_read_json(paths["calibration_dashboard"]),
        full_report=_read_json(paths["full_report"]),
        selected_date=selected_date,
        paths=paths,
        missing_files=missing,
    )


def latest_output_date(data_root: str | Path = "data") -> str:
    outputs = Path(data_root) / "outputs"
    if not outputs.exists():
        return ""
    dated_dirs = sorted([path.name for path in outputs.iterdir() if path.is_dir()], reverse=True)
    return dated_dirs[0] if dated_dirs else ""


def available_output_dates(data_root: str | Path = "data") -> list[str]:
    outputs = Path(data_root) / "outputs"
    if not outputs.exists():
        return []
    return sorted([path.name for path in outputs.iterdir() if path.is_dir()], reverse=True)


def _read_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    with file_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _read_text(path: str) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")

