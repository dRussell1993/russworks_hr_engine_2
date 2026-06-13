from __future__ import annotations

from typing import Any, Mapping, Sequence

from .loaders import DashboardData


def overview_metrics(data: DashboardData) -> list[dict[str, Any]]:
    metadata = _mapping(data.dashboard_data.get("metadata")) or _mapping(data.full_report.get("context"))
    command = _mapping(data.command_center)
    slate = _mapping(command.get("slate_status"))
    execution = _mapping(command.get("execution_summary"))
    return [
        {"Metric": "Date", "Value": metadata.get("report_date") or data.selected_date},
        {"Metric": "Validation", "Value": metadata.get("validation_status", "")},
        {"Metric": "Games reviewed", "Value": metadata.get("games_reviewed", slate.get("games_loaded", 0))},
        {"Metric": "Batters loaded", "Value": slate.get("batters_loaded", len(data.dashboard_data.get("batters", []) or []))},
        {"Metric": "Reports generated", "Value": len(execution.get("reports_generated", []) or [])},
        {"Metric": "Exports generated", "Value": len(execution.get("exports_generated", []) or [])},
    ]


def top_hr_targets(data: DashboardData, *, limit: int = 25) -> list[dict[str, Any]]:
    batters = list(data.dashboard_data.get("batters", []) or [])
    batters.sort(key=lambda row: float(row.get("russ_score", 0.0) or 0.0), reverse=True)
    return [
        {
            "Rank": row.get("rank", index),
            "Batter": row.get("batter", ""),
            "Team": row.get("team", ""),
            "Slot": row.get("lineup_slot", ""),
            "Russ Score": row.get("russ_score", 0.0),
            "Tier": row.get("tier", ""),
            "Confidence": _confidence_label(row),
            "Key Factors": ", ".join(row.get("key_factors", []) or []),
        }
        for index, row in enumerate(batters[:limit], start=1)
    ]


def team_clusters(data: DashboardData) -> list[dict[str, Any]]:
    return [
        {
            "Rank": row.get("rank", ""),
            "Team": row.get("team", ""),
            "Opponent": row.get("opponent", ""),
            "TAG": row.get("tag_grade", ""),
            "CPS": row.get("cps_grade", ""),
            "Cluster Score": row.get("total_cluster_score", 0.0),
            "Label": row.get("cluster_strength_label", ""),
            "Captain": row.get("cluster_captain", ""),
            "Hidden Beneficiary": row.get("hidden_cluster_beneficiary", ""),
            "Confidence": row.get("confidence_grade", ""),
        }
        for row in data.dashboard_data.get("teams", []) or []
    ]


def slip_cards(data: DashboardData) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for slip in data.dashboard_data.get("slips", []) or []:
        slip_type = _title(str(slip.get("slip_type", "other")).replace("_", " "))
        grouped.setdefault(slip_type, []).append(
            {
                "name": slip.get("name", ""),
                "confidence": _confidence_label(slip),
                "batters": list(slip.get("batters", []) or []),
                "teams": list(slip.get("teams", []) or []),
                "justification": slip.get("justification", ""),
            }
        )
    return grouped


def confidence_rows(data: DashboardData) -> list[dict[str, Any]]:
    views = _mapping(data.dashboard_data.get("confidence_views"))
    grade_counts = _mapping(views.get("batter_confidence_grade_counts"))
    command_confidence = _mapping(views.get("command_center_confidence"))
    rows = [{"Area": "Batter Confidence", "Metric": grade, "Value": count} for grade, count in sorted(grade_counts.items())]
    for key, value in command_confidence.items():
        rows.append({"Area": "Command Center", "Metric": key.replace("_", " ").title(), "Value": value})
    return rows


def risk_rows(data: DashboardData) -> list[dict[str, Any]]:
    portfolio = _mapping(data.dashboard_data.get("portfolio"))
    simulation = _mapping(data.dashboard_data.get("simulation"))
    rows = [
        {"Area": "Portfolio", "Metric": "Risk Grade", "Value": portfolio.get("risk_grade", "")},
        {"Area": "Portfolio", "Metric": "Risk Score", "Value": portfolio.get("risk_score", 0.0)},
        {"Area": "Simulation", "Metric": "Expected Hit Rate", "Value": simulation.get("expected_hit_rate", 0.0)},
        {"Area": "Simulation", "Metric": "Expected ROI", "Value": simulation.get("expected_roi", 0.0)},
        {"Area": "Simulation", "Metric": "Drawdown Risk", "Value": simulation.get("drawdown_risk", 0.0)},
        {"Area": "Simulation", "Metric": "Risk Grade", "Value": simulation.get("risk_grade", "")},
    ]
    return rows


def validation_warning_rows(data: DashboardData) -> list[dict[str, Any]]:
    command = _mapping(data.command_center or data.dashboard_data.get("command_center"))
    slate = _mapping(command.get("slate_status"))
    rows = [{"Type": "Warning", "Message": warning} for warning in command.get("warnings", []) or []]
    for game in slate.get("skipped_games", []) or []:
        rows.append(
            {
                "Type": "Skipped Game",
                "Message": f"{game.get('game_id', '')}: {'; '.join(game.get('skipped_reason', []) or [])}",
            }
        )
    for summary in data.calibration_dashboard.get("validation_summaries", []) or []:
        rows.append({"Type": "Validation Summary", "Message": summary})
    if not rows:
        rows.append({"Type": "Status", "Message": "No validation warnings found."})
    return rows


def command_center_rows(data: DashboardData) -> list[dict[str, Any]]:
    command = _mapping(data.command_center or data.dashboard_data.get("command_center"))
    slate = _mapping(command.get("slate_status"))
    execution = _mapping(command.get("execution_summary"))
    formula = _mapping(command.get("formula_health"))
    rows = []
    for key, value in slate.items():
        if key not in {"provider_health", "skipped_games", "validation_failures"}:
            rows.append({"Section": "Slate", "Metric": key.replace("_", " ").title(), "Value": _display(value)})
    for key, value in execution.items():
        if key not in {"errors", "warnings"}:
            rows.append({"Section": "Execution", "Metric": key.replace("_", " ").title(), "Value": _display(value)})
    for key, value in formula.items():
        if key.endswith("_summary") or key in {"modules_heating_up", "modules_cooling_off"}:
            rows.append({"Section": "Formula", "Metric": key.replace("_", " ").title(), "Value": _display(value)})
    return rows


def operator_report_preview(data: DashboardData, *, lines: int = 80) -> str:
    return "\n".join(data.operator_report.splitlines()[:lines])


def _confidence_label(row: Mapping[str, Any]) -> str:
    grade = row.get("confidence_grade", "")
    score = row.get("confidence_score", "")
    return f"{grade} {score}".strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _display(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return str(value)


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())

