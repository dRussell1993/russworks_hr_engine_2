from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class OutputRootCandidate:
    root: Path
    available_dates: list[str] = field(default_factory=list)
    has_dashboard_data: bool = False
    has_command_center: bool = False
    has_dashboard: bool = False

    @property
    def score(self) -> int:
        return len(self.available_dates) * 3 + int(self.has_dashboard_data) + int(self.has_command_center) + int(self.has_dashboard)


@dataclass(frozen=True)
class OutputDiscovery:
    selected_root: Path
    selected_date: str = ""
    candidates: list[OutputRootCandidate] = field(default_factory=list)
    searched_paths: list[str] = field(default_factory=list)

    @property
    def available_dates(self) -> list[str]:
        dates: set[str] = set()
        for candidate in self.candidates:
            dates.update(candidate.available_dates)
        return sorted(dates, reverse=True)


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
    data_root: str = ""
    searched_paths: list[str] = field(default_factory=list)
    available_dates: list[str] = field(default_factory=list)

    @property
    def missing_output_message(self) -> str:
        if not self.missing_files:
            return ""
        searched = "\n".join(f"- {path}" for path in self.searched_paths)
        return (
            "Missing Russ-Works dashboard outputs.\n\n"
            f"Missing files: {', '.join(self.missing_files)}\n\n"
            "Searched paths:\n"
            f"{searched}\n\n"
            "Next command:\n"
            "python -m russworks.run --date YYYY-MM-DD"
        )


def discover_outputs(
    *,
    start: str | Path | None = None,
    manual_root: str | Path | None = None,
    date: str | None = None,
) -> OutputDiscovery:
    start_path = Path(start or Path.cwd()).resolve()
    searched_roots = _candidate_roots(start_path, manual_root=manual_root)
    candidates = [_candidate(root) for root in searched_roots]
    if manual_root:
        selected_root = Path(manual_root).expanduser().resolve()
        selected_date = date or latest_output_date(selected_root) or _latest_date(candidates)
    else:
        selected_date = date or _latest_date(candidates)
        selected_root = _select_root(candidates, selected_date)
    return OutputDiscovery(
        selected_root=selected_root,
        selected_date=selected_date,
        candidates=candidates,
        searched_paths=[str(root) for root in searched_roots],
    )


def load_dashboard_outputs(
    *,
    date: str | None = None,
    data_root: str | Path | None = None,
    start: str | Path | None = None,
) -> DashboardData:
    discovery = discover_outputs(start=start, manual_root=data_root, date=date)
    root = discovery.selected_root
    selected_date = discovery.selected_date
    paths = {
        "dashboard_data": str(root / "web" / "dashboard_data.json"),
        "operator_report": str(root / "outputs" / selected_date / "russworks_operator_report.md") if selected_date else "",
        "command_center": str(root / "command_center" / "command_center.json"),
        "calibration_dashboard": str(root / "dashboard" / "dashboard.json"),
        "full_report": str(root / "outputs" / selected_date / "russworks_full_report.json") if selected_date else "",
    }
    missing = [name for name, path in paths.items() if path and not Path(path).exists()]
    if not selected_date:
        missing.append("report_date")
    return DashboardData(
        dashboard_data=_read_json(paths["dashboard_data"]),
        operator_report=_read_text(paths["operator_report"]),
        command_center=_read_json(paths["command_center"]),
        calibration_dashboard=_read_json(paths["calibration_dashboard"]),
        full_report=_read_json(paths["full_report"]),
        selected_date=selected_date,
        paths=paths,
        missing_files=sorted(set(missing)),
        data_root=str(root),
        searched_paths=discovery.searched_paths,
        available_dates=discovery.available_dates,
    )


def latest_output_date(data_root: str | Path = "data") -> str:
    return _dates_for_root(Path(data_root))[0] if _dates_for_root(Path(data_root)) else ""


def available_output_dates(data_root: str | Path = "data") -> list[str]:
    return _dates_for_root(Path(data_root))


def _candidate_roots(start: Path, *, manual_root: str | Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if manual_root:
        roots.append(Path(manual_root).expanduser().resolve())
    for base in _search_bases(start):
        roots.append((base / "data").resolve())
        work_dir = base / "work"
        if work_dir.exists():
            roots.extend(path.resolve() for path in work_dir.glob("**/data") if path.is_dir())
    roots.append((Path.cwd() / "data").resolve())
    return _unique_existing_or_requested(roots)


def _search_bases(start: Path) -> list[Path]:
    bases = [start, *start.parents]
    return bases[:6]


def _unique_existing_or_requested(paths: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _candidate(root: Path) -> OutputRootCandidate:
    return OutputRootCandidate(
        root=root,
        available_dates=_dates_for_root(root),
        has_dashboard_data=(root / "web" / "dashboard_data.json").exists(),
        has_command_center=(root / "command_center" / "command_center.json").exists(),
        has_dashboard=(root / "dashboard" / "dashboard.json").exists(),
    )


def _dates_for_root(root: Path) -> list[str]:
    outputs = root / "outputs"
    if not outputs.exists():
        return []
    return sorted([path.name for path in outputs.iterdir() if path.is_dir()], reverse=True)


def _latest_date(candidates: Iterable[OutputRootCandidate]) -> str:
    dates: set[str] = set()
    for candidate in candidates:
        dates.update(candidate.available_dates)
    return sorted(dates, reverse=True)[0] if dates else ""


def _select_root(candidates: list[OutputRootCandidate], selected_date: str) -> Path:
    if not candidates:
        return Path("data").resolve()
    with_date = [candidate for candidate in candidates if selected_date and selected_date in candidate.available_dates]
    pool = with_date or candidates
    return max(pool, key=lambda candidate: candidate.score).root


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
