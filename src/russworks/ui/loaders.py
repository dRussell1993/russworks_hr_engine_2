from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


SOURCE_REAL_PROJECT = "Real project output"
SOURCE_WORKTREE_SAMPLE = "Worktree/sample output"
SOURCE_TEST = "Test output"
PLACEHOLDER_PATTERNS = ("KC Batter", "TEX Batter")


@dataclass(frozen=True)
class OutputRootCandidate:
    root: Path
    available_dates: list[str] = field(default_factory=list)
    has_dashboard_data: bool = False
    has_command_center: bool = False
    has_dashboard: bool = False
    source_label: str = SOURCE_WORKTREE_SAMPLE
    priority: int = 0

    @property
    def score(self) -> int:
        return len(self.available_dates) * 3 + int(self.has_dashboard_data) + int(self.has_command_center) + int(self.has_dashboard)


@dataclass(frozen=True)
class OutputDiscovery:
    selected_root: Path
    selected_date: str = ""
    source_label: str = SOURCE_WORKTREE_SAMPLE
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
    source_label: str = SOURCE_WORKTREE_SAMPLE
    searched_paths: list[str] = field(default_factory=list)
    available_dates: list[str] = field(default_factory=list)
    placeholder_warnings: list[str] = field(default_factory=list)
    postmortem_status: dict[str, Any] = field(default_factory=dict)

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
    repo_root = _repo_root(start_path)
    searched_roots = _candidate_roots(start_path, manual_root=manual_root, repo_root=repo_root)
    candidates = [_candidate(root, repo_root=repo_root, manual_root=manual_root) for root in searched_roots]
    if manual_root:
        selected_root = Path(manual_root).expanduser().resolve()
        selected_date = date or latest_output_date(selected_root) or _latest_date(candidates)
        source_label = _source_label(selected_root, repo_root=repo_root, manual_root=manual_root)
    else:
        selected_root = _select_root(candidates, date)
        selected_date = date or latest_output_date(selected_root) or _latest_date(candidates)
        source_label = next((candidate.source_label for candidate in candidates if candidate.root == selected_root), _source_label(selected_root, repo_root=repo_root))
    return OutputDiscovery(
        selected_root=selected_root,
        selected_date=selected_date,
        source_label=source_label,
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
    dashboard_data = _read_json(paths["dashboard_data"])
    command_center = _read_json(paths["command_center"])
    calibration_dashboard = _read_json(paths["calibration_dashboard"])
    full_report = _read_json(paths["full_report"])
    return DashboardData(
        dashboard_data=dashboard_data,
        operator_report=_read_text(paths["operator_report"]),
        command_center=command_center,
        calibration_dashboard=calibration_dashboard,
        full_report=full_report,
        selected_date=selected_date,
        paths=paths,
        missing_files=sorted(set(missing)),
        data_root=str(root),
        source_label=discovery.source_label,
        searched_paths=discovery.searched_paths,
        available_dates=discovery.available_dates,
        placeholder_warnings=_placeholder_warnings(dashboard_data, command_center, calibration_dashboard, full_report),
        postmortem_status=_postmortem_status(root, selected_date),
    )


def latest_output_date(data_root: str | Path = "data") -> str:
    return _dates_for_root(Path(data_root))[0] if _dates_for_root(Path(data_root)) else ""


def available_output_dates(data_root: str | Path = "data") -> list[str]:
    return _dates_for_root(Path(data_root))


def _candidate_roots(start: Path, *, manual_root: str | Path | None = None, repo_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if manual_root:
        roots.append(Path(manual_root).expanduser().resolve())
    if repo_root:
        roots.append((repo_root / "data").resolve())
    for base in _search_bases(start):
        roots.append((base / "data").resolve())
    cwd = Path.cwd().resolve()
    if start == cwd or cwd in start.parents:
        roots.append((cwd / "data").resolve())
    for base in _search_bases(start):
        work_dir = base / "work"
        if work_dir.exists():
            roots.extend(path.resolve() for path in work_dir.glob("**/data") if path.is_dir())
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


def _candidate(root: Path, *, repo_root: Path | None = None, manual_root: str | Path | None = None) -> OutputRootCandidate:
    label = _source_label(root, repo_root=repo_root, manual_root=manual_root)
    return OutputRootCandidate(
        root=root,
        available_dates=_dates_for_root(root),
        has_dashboard_data=(root / "web" / "dashboard_data.json").exists(),
        has_command_center=(root / "command_center" / "command_center.json").exists(),
        has_dashboard=(root / "dashboard" / "dashboard.json").exists(),
        source_label=label,
        priority=_source_priority(label),
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


def _select_root(candidates: list[OutputRootCandidate], selected_date: str | None) -> Path:
    if not candidates:
        return Path("data").resolve()
    with_date = [candidate for candidate in candidates if selected_date and selected_date in candidate.available_dates]
    pool = with_date or [candidate for candidate in candidates if candidate.score > 0] or candidates
    return max(pool, key=lambda candidate: (candidate.priority, candidate.score, len(candidate.available_dates))).root


def _repo_root(start: Path) -> Path | None:
    for path in [start, *start.parents]:
        if (path / "pyproject.toml").exists() and (path / "src" / "russworks").exists():
            return path.resolve()
    return None


def _source_label(root: Path, *, repo_root: Path | None = None, manual_root: str | Path | None = None) -> str:
    resolved = root.resolve()
    if repo_root and resolved == (repo_root / "data").resolve():
        return SOURCE_REAL_PROJECT
    if _looks_like_test_path(resolved):
        return SOURCE_TEST
    if manual_root and resolved == Path(manual_root).expanduser().resolve():
        return SOURCE_REAL_PROJECT if _is_project_data_root(resolved) else SOURCE_WORKTREE_SAMPLE
    if _is_project_data_root(resolved):
        return SOURCE_REAL_PROJECT
    return SOURCE_WORKTREE_SAMPLE


def _source_priority(label: str) -> int:
    return {
        SOURCE_REAL_PROJECT: 30,
        SOURCE_WORKTREE_SAMPLE: 20,
        SOURCE_TEST: 10,
    }.get(label, 0)


def _looks_like_test_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return any("pytest" in part or part.startswith("tmp") or part in {"temp", "tests", "test"} for part in parts)


def _is_project_data_root(root: Path) -> bool:
    parent = root.parent
    return root.name == "data" and (parent / "pyproject.toml").exists() and (parent / "src" / "russworks").exists()


def _placeholder_warnings(*payloads: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for value in payloads:
        for text in _walk_strings(value):
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern.lower() in text.lower():
                    message = f"Placeholder-looking data detected: {text}"
                    if message not in warnings:
                        warnings.append(message)
    return warnings


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, list | tuple | set):
        for nested in value:
            yield from _walk_strings(nested)


def _postmortem_status(root: Path, selected_date: str) -> dict[str, Any]:
    date = selected_date or "YYYY-MM-DD"
    postmortem_root = root / "postmortem"
    normalized_actual = postmortem_root / f"actual_home_runs_{date}.csv"
    raw_actual = postmortem_root / f"actual_home_runs_raw_{date}.csv"
    actual_path = normalized_actual if normalized_actual.exists() else raw_actual
    report_path = postmortem_root / date / "postmortem_report.json"
    calibration_path = postmortem_root / date / "calibration_result.json"
    dashboard_path = root / "dashboard" / "dashboard.json"
    recommendations_path = root / "recommendations" / "recommendations.json"
    last_run_date = date if report_path.exists() else _latest_postmortem_run_date(postmortem_root)
    return {
        "date": date,
        "actual_hr_file_found": actual_path.exists(),
        "actual_hr_file_path": str(actual_path),
        "normalized_actual_hr_file_path": str(normalized_actual),
        "raw_actual_hr_file_path": str(raw_actual),
        "postmortem_report_found": report_path.exists(),
        "postmortem_report_path": str(report_path),
        "postmortem_last_run_date": last_run_date,
        "winner_log_path": f"{report_path}#winner_log",
        "loser_log_path": f"{report_path}#loser_log",
        "calibration_export_found": calibration_path.exists(),
        "calibration_export_path": str(calibration_path),
        "dashboard_export_found": dashboard_path.exists(),
        "dashboard_export_path": str(dashboard_path),
        "recommendation_export_found": recommendations_path.exists(),
        "recommendation_export_path": str(recommendations_path),
        "runner_command": f"python -m russworks.postmortem.run --date {date}",
    }


def _latest_postmortem_run_date(postmortem_root: Path) -> str:
    if not postmortem_root.exists():
        return ""
    dated = [path.name for path in postmortem_root.iterdir() if path.is_dir() and (path / "postmortem_report.json").exists()]
    return sorted(dated, reverse=True)[0] if dated else ""


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
