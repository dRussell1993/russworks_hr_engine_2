from __future__ import annotations

from typing import Any, Mapping

from russworks.ui.loaders import DashboardData


SLIP_GROUP_ORDER = ["Core", "Non-Superstar Core", "Balanced", "Chaos", "Contrarian"]


def overview_metrics(data: DashboardData) -> list[dict[str, Any]]:
    metadata = _mapping(data.dashboard_data.get("metadata")) or _mapping(data.full_report.get("context"))
    command = _mapping(data.command_center)
    slate = _mapping(command.get("slate_status"))
    execution = _mapping(command.get("execution_summary"))
    validation = _mapping(metadata.get("validation_summary")) or _mapping(slate.get("validation_summary"))
    return [
        {"Metric": "Date", "Value": metadata.get("report_date") or data.selected_date},
        {"Metric": "Data source", "Value": data.source_label},
        {"Metric": "Validation", "Value": metadata.get("validation_status", "")},
        {"Metric": "Games reviewed", "Value": metadata.get("games_reviewed", slate.get("games_loaded", 0))},
        {"Metric": "Batters loaded", "Value": slate.get("batters_loaded", len(data.dashboard_data.get("batters", []) or []))},
        {"Metric": "Skipped games", "Value": validation.get("skipped_games", len(slate.get("skipped_games", []) or []))},
        {"Metric": "Park fallback games", "Value": validation.get("park_factor_fallback_games", 0)},
        {"Metric": "Reports generated", "Value": len(execution.get("reports_generated", []) or [])},
        {"Metric": "Exports generated", "Value": len(execution.get("exports_generated", []) or [])},
    ]


def filter_options(data: DashboardData) -> dict[str, list[str]]:
    rows = _enhanced_batter_rows(data)
    return {
        "teams": sorted({str(row.get("Team", "")) for row in rows if row.get("Team")}),
        "tiers": sorted({str(row.get("Tier", "")) for row in rows if row.get("Tier")}),
        "confidence": sorted({str(row.get("Confidence Grade", "")) for row in rows if row.get("Confidence Grade")}),
    }


def top_hr_targets(
    data: DashboardData,
    *,
    limit: int = 25,
    team: str = "",
    tier: str = "",
    confidence: str = "",
    non_superstar_only: bool = False,
) -> list[dict[str, Any]]:
    rows = _enhanced_batter_rows(data)
    if team:
        rows = [row for row in rows if row.get("Team") == team]
    if tier:
        rows = [row for row in rows if row.get("Tier") == tier]
    if confidence:
        rows = [row for row in rows if row.get("Confidence Grade") == confidence]
    if non_superstar_only:
        rows = [row for row in rows if row.get("Non-Superstar Core")]
    rows.sort(key=lambda row: float(row.get("Russ Score", 0.0) or 0.0), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["Rank"] = index
    return rows[:limit]


def team_clusters(data: DashboardData) -> list[dict[str, Any]]:
    warnings = validation_warning_rows(data)
    warning_text = "; ".join(row["Message"] for row in warnings if row.get("Type") in {"Skipped Game", "Fallback"})
    return [
        {
            "Rank": row.get("rank", index),
            "Team": row.get("team", ""),
            "Opponent": row.get("opponent", ""),
            "TAG": row.get("tag_grade", ""),
            "CPS": row.get("cps_grade", ""),
            "Cluster Score": row.get("total_cluster_score", 0.0),
            "Label": row.get("cluster_strength_label", ""),
            "Captain": row.get("cluster_captain", ""),
            "Hidden Beneficiary": row.get("hidden_cluster_beneficiary", ""),
            "Confidence": row.get("confidence_grade", ""),
            "Warnings": warning_text,
        }
        for index, row in enumerate(data.dashboard_data.get("teams", []) or [], start=1)
    ]


def cluster_cards(data: DashboardData) -> list[dict[str, Any]]:
    return team_clusters(data)


def slip_cards(data: DashboardData) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in SLIP_GROUP_ORDER}
    rich_slips = _full_report_slips(data)
    if rich_slips:
        for slip in rich_slips:
            group = _slip_group(str(slip.get("slip_type", "")))
            grouped.setdefault(group, []).append(_rich_slip_card(slip))
    else:
        for slip in data.dashboard_data.get("slips", []) or []:
            group = _slip_group(str(slip.get("slip_type", "")))
            grouped.setdefault(group, []).append(_basic_slip_card(slip))
    return {group: cards for group, cards in grouped.items() if cards}


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
    return [
        {"Area": "Portfolio", "Metric": "Risk Grade", "Value": portfolio.get("risk_grade", "")},
        {"Area": "Portfolio", "Metric": "Risk Score", "Value": portfolio.get("risk_score", 0.0)},
        {"Area": "Simulation", "Metric": "Simulation Count", "Value": simulation.get("simulation_count", 0)},
        {"Area": "Simulation", "Metric": "Expected Hit Rate", "Value": simulation.get("expected_hit_rate", 0.0)},
        {"Area": "Simulation", "Metric": "Expected ROI", "Value": simulation.get("expected_roi", 0.0)},
        {"Area": "Simulation", "Metric": "Drawdown Risk", "Value": simulation.get("drawdown_risk", 0.0)},
        {"Area": "Simulation", "Metric": "Portfolio Volatility", "Value": simulation.get("portfolio_volatility", 0.0)},
        {"Area": "Simulation", "Metric": "Risk Grade", "Value": simulation.get("risk_grade", "")},
    ]


def exposure_warning_rows(data: DashboardData) -> list[dict[str, Any]]:
    portfolio = _mapping(data.dashboard_data.get("portfolio"))
    full_portfolio = _mapping(data.full_report.get("portfolio"))
    diversification = _mapping(data.full_report.get("diversification"))
    rows = []
    for message in [*(portfolio.get("recommendations", []) or []), *(full_portfolio.get("recommendations", []) or [])]:
        rows.append({"Type": "Portfolio", "Message": _message(message)})
    for message in portfolio.get("diversification_recommendations", []) or []:
        rows.append({"Type": "Diversification", "Message": _message(message)})
    for message in diversification.get("recommendations", []) or []:
        rows.append({"Type": "Diversification", "Message": _message(message)})
    if not rows:
        rows.append({"Type": "Status", "Message": "No exposure warnings found."})
    return rows


def accuracy_metric_rows(data: DashboardData) -> list[dict[str, Any]]:
    accuracy = accuracy_review(data)
    if not accuracy:
        return []
    return [
        {"Metric": "HR Events Acquired", "Value": accuracy.get("hr_events_acquired", 0)},
        {"Metric": "Winners", "Value": accuracy.get("winners", 0)},
        {"Metric": "Misses", "Value": accuracy.get("misses", 0)},
        {"Metric": "False Positives", "Value": accuracy.get("false_positives", 0)},
        {"Metric": "Hit Rate", "Value": _percent(accuracy.get("hit_rate", 0.0))},
    ]


def accuracy_hit_rate_sections(data: DashboardData) -> dict[str, list[dict[str, Any]]]:
    accuracy = accuracy_review(data)
    return {
        "By Russ Tier": _accuracy_bucket_rows(accuracy.get("hit_rate_by_russ_tier", []) if accuracy else []),
        "By Confidence Grade": _accuracy_bucket_rows(accuracy.get("hit_rate_by_confidence_grade", []) if accuracy else []),
        "By Team Cluster Grade": _accuracy_bucket_rows(accuracy.get("hit_rate_by_team_cluster_grade", []) if accuracy else []),
        "By Slip Type": _accuracy_bucket_rows(accuracy.get("hit_rate_by_slip_type", []) if accuracy else []),
    }


def accuracy_false_positive_rows(data: DashboardData) -> list[dict[str, Any]]:
    accuracy = accuracy_review(data)
    rows = []
    for item in accuracy.get("top_false_positives", []) if accuracy else []:
        row = _mapping(item)
        rows.append(
            {
                "Batter": row.get("batter", ""),
                "Team": row.get("team", ""),
                "Slip": row.get("slip_name", ""),
                "Slip Type": row.get("slip_type", ""),
                "Russ Score": row.get("russ_score", 0.0),
                "Overweighted Modules": ", ".join(str(value) for value in row.get("overweighted_modules", []) or []),
                "Reason": row.get("reason", ""),
            }
        )
    return rows


def accuracy_false_negative_rows(data: DashboardData) -> list[dict[str, Any]]:
    accuracy = accuracy_review(data)
    rows = []
    for item in accuracy.get("top_false_negatives", []) if accuracy else []:
        row = _mapping(item)
        rows.append(
            {
                "Batter": row.get("batter", ""),
                "Team": row.get("team", ""),
                "Pitcher": row.get("pitcher", ""),
                "Pitch": row.get("pitch", ""),
                "Inning": row.get("inning", ""),
                "Distance": row.get("distance", ""),
                "Russ Score": row.get("russ_score", 0.0),
                "Tier": row.get("tier", ""),
                "Confidence": row.get("confidence", ""),
            }
        )
    return rows


def accuracy_module_rows(data: DashboardData) -> list[dict[str, Any]]:
    accuracy = accuracy_review(data)
    rows = []
    for section, items in [
        ("Best", accuracy.get("best_performing_modules", []) if accuracy else []),
        ("Worst", accuracy.get("worst_performing_modules", []) if accuracy else []),
    ]:
        for item in items:
            row = _mapping(item)
            rows.append(
                {
                    "Section": section,
                    "Module": row.get("module", ""),
                    "Appearances": row.get("appearances", 0),
                    "Wins": row.get("wins", 0),
                    "Losses": row.get("losses", 0),
                    "Hit Rate": _percent(row.get("hit_rate", 0.0)),
                    "False Positives": row.get("false_positives", 0),
                    "False Negatives": row.get("false_negatives", 0),
                    "Confidence Accuracy": _percent(row.get("confidence_accuracy", 0.0)),
                }
            )
    return rows


def accuracy_recommendation_rows(data: DashboardData) -> list[dict[str, Any]]:
    accuracy = accuracy_review(data)
    rows = []
    for item in accuracy.get("top_calibration_recommendations", []) if accuracy else []:
        row = _mapping(item)
        rows.append(
            {
                "Module": row.get("module", ""),
                "Action": row.get("action", ""),
                "Confidence": row.get("confidence", ""),
                "Reasoning": row.get("reasoning", ""),
                "Source": row.get("source", ""),
            }
        )
    return rows


def accuracy_review(data: DashboardData) -> dict[str, Any]:
    accuracy = _mapping(data.dashboard_data.get("accuracy_review"))
    if accuracy:
        return accuracy
    accuracy = _mapping(data.calibration_dashboard.get("accuracy_review"))
    if accuracy:
        return accuracy
    return _mapping(_mapping(_mapping(data.command_center).get("formula_health")).get("accuracy_review"))


def validation_warning_rows(data: DashboardData) -> list[dict[str, Any]]:
    command = _mapping(data.command_center or data.dashboard_data.get("command_center"))
    slate = _mapping(command.get("slate_status"))
    summary = _mapping(slate.get("validation_summary"))
    rows = []
    for warning in data.placeholder_warnings:
        rows.append({"Type": "Placeholder Data", "Message": warning})
    for warning in command.get("warnings", []) or []:
        warning_type = "Fallback" if "Neutral park factor fallback" in str(warning) else "Warning"
        rows.append({"Type": warning_type, "Message": warning})
    for game in slate.get("skipped_games", []) or []:
        rows.append(
            {
                "Type": "Skipped Game",
                "Message": f"{game.get('game_id', '')}: {'; '.join(game.get('skipped_reason', []) or [])}",
            }
        )
    for game_id in summary.get("park_factor_fallback_game_ids", []) or []:
        message = f"{game_id}: Neutral park factor fallback used"
        if not any(row["Message"] == message for row in rows):
            rows.append({"Type": "Fallback", "Message": message})
    failures = _mapping(slate.get("validation_failures"))
    for key, values in failures.items():
        rows.append({"Type": "Missing Data", "Message": f"{key}: {', '.join(str(value) for value in values)}"})
    for summary_text in data.calibration_dashboard.get("validation_summaries", []) or []:
        rows.append({"Type": "Validation Summary", "Message": summary_text})
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


def provider_health_rows(data: DashboardData) -> list[dict[str, Any]]:
    command = _mapping(data.command_center or data.dashboard_data.get("command_center"))
    return list(_mapping(command.get("slate_status")).get("provider_health", []) or [])


def generated_output_rows(data: DashboardData) -> list[dict[str, Any]]:
    execution = _mapping(_mapping(data.command_center).get("execution_summary"))
    rows = []
    for path in execution.get("reports_generated", []) or []:
        rows.append({"Type": "Report", "Path": path})
    for path in execution.get("exports_generated", []) or []:
        rows.append({"Type": "Export", "Path": path})
    for name, path in data.paths.items():
        rows.append({"Type": name, "Path": path})
    return rows


def data_source_rows(data: DashboardData) -> list[dict[str, Any]]:
    return [
        {"Metric": "Data Source", "Value": data.source_label},
        {"Metric": "Active Data Root", "Value": data.data_root},
        {"Metric": "Report Date", "Value": data.selected_date},
    ]


def postmortem_status_rows(data: DashboardData) -> list[dict[str, Any]]:
    status = data.postmortem_status or {}
    return [
        {"Metric": "Actual HR File", "Status": _found(status.get("actual_hr_file_found")), "Path": status.get("actual_hr_file_path", "")},
        {"Metric": "Post-Mortem Last Run Date", "Status": status.get("postmortem_last_run_date") or "Missing", "Path": status.get("postmortem_report_path", "")},
        {"Metric": "Winner Log", "Status": _found(status.get("postmortem_report_found")), "Path": status.get("winner_log_path", "")},
        {"Metric": "Loser Log", "Status": _found(status.get("postmortem_report_found")), "Path": status.get("loser_log_path", "")},
        {"Metric": "Calibration Export", "Status": _found(status.get("calibration_export_found")), "Path": status.get("calibration_export_path", "")},
        {"Metric": "Dashboard Export", "Status": _found(status.get("dashboard_export_found")), "Path": status.get("dashboard_export_path", "")},
        {"Metric": "Recommendation Export", "Status": _found(status.get("recommendation_export_found")), "Path": status.get("recommendation_export_path", "")},
    ]


def postmortem_command(data: DashboardData) -> str:
    return str((data.postmortem_status or {}).get("runner_command") or "python -m russworks.postmortem.run --date YYYY-MM-DD")


def scheduler_rows(data: DashboardData) -> list[dict[str, Any]]:
    scheduler = _mapping(data.dashboard_data.get("scheduler"))
    tasks = scheduler.get("tasks", []) or []
    if tasks:
        return list(tasks)
    summary = _mapping(_mapping(_mapping(data.command_center).get("formula_health")).get("scheduler_summary"))
    return [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in summary.items()]


def operator_report_preview(data: DashboardData, *, lines: int = 80) -> str:
    return "\n".join(data.operator_report.splitlines()[:lines])


def missing_output_rows(data: DashboardData) -> list[dict[str, Any]]:
    return [{"Missing": name, "Expected Path": data.paths.get(name, "")} for name in data.missing_files]


def placeholder_warning_rows(data: DashboardData) -> list[dict[str, Any]]:
    return [{"Warning": warning} for warning in data.placeholder_warnings]


def _enhanced_batter_rows(data: DashboardData) -> list[dict[str, Any]]:
    full_by_key = {
        (str(row.get("batter", "")), str(row.get("team", ""))): row
        for row in _mapping(data.full_report.get("step3")).get("batter_reviews", []) or []
    }
    rows = []
    for index, row in enumerate(data.dashboard_data.get("batters", []) or [], start=1):
        rich = full_by_key.get((str(row.get("batter", "")), str(row.get("team", ""))), {})
        confidence = _mapping(rich.get("confidence"))
        drivers = _key_drivers(row, rich)
        rows.append(
            {
                "Rank": row.get("rank", index),
                "Batter": row.get("batter", ""),
                "Team": row.get("team", ""),
                "Opponent": row.get("opponent", ""),
                "Lineup Slot": row.get("lineup_slot", ""),
                "Russ Score": row.get("russ_score", rich.get("russ_score", 0.0)),
                "Tier": rich.get("score_band") or row.get("tier", ""),
                "Confidence": _confidence_label(row),
                "Confidence Grade": row.get("confidence_grade") or confidence.get("grade", ""),
                "Key Drivers": ", ".join(drivers),
                "Non-Superstar Core": bool(rich.get("non_superstar_core") or "non_superstar_core" in row.get("key_factors", [])),
            }
        )
    return rows


def _key_drivers(row: Mapping[str, Any], rich: Mapping[str, Any]) -> list[str]:
    drivers = [str(item).replace("_", " ").title() for item in row.get("key_factors", []) or []]
    for key, label in [
        ("tag_contribution", "TAG"),
        ("cps_contribution", "CPS"),
        ("pvs_contribution", "PVS"),
    ]:
        value = rich.get(key)
        if isinstance(value, (int, float)) and value:
            drivers.append(f"{label} {round(float(value), 1)}")
    return drivers


def _full_report_slips(data: DashboardData) -> list[dict[str, Any]]:
    step5 = _mapping(data.full_report.get("step5"))
    slips: list[dict[str, Any]] = []
    for bucket in ["core_slips", "non_superstar_core_slips", "balanced_slips", "chaos_slips", "contrarian_slips"]:
        for row in step5.get(bucket, []) or []:
            slips.append(dict(row, slip_bucket=bucket))
    return slips


def _rich_slip_card(slip: Mapping[str, Any]) -> dict[str, Any]:
    confidence = _mapping(slip.get("confidence"))
    return {
        "name": slip.get("name", ""),
        "confidence": f"{confidence.get('grade', '')} {confidence.get('score', '')}".strip(),
        "legs": [
            {
                "Batter": leg.get("batter", ""),
                "Team": leg.get("team", ""),
                "Russ Score": leg.get("russ_score", 0.0),
                "Confidence": _confidence_label(_mapping(leg.get("confidence"))),
                "Role": leg.get("slip_role", ""),
                "Reasoning": leg.get("justification", ""),
            }
            for leg in slip.get("legs", []) or []
        ],
        "teams": sorted({str(leg.get("team", "")) for leg in slip.get("legs", []) or [] if leg.get("team")}),
        "justification": slip.get("justification", ""),
        "risk_warning": _risk_warning(slip),
    }


def _basic_slip_card(slip: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": slip.get("name", ""),
        "confidence": _confidence_label(slip),
        "legs": [{"Batter": batter, "Team": "", "Russ Score": "", "Confidence": "", "Role": "", "Reasoning": ""} for batter in slip.get("batters", []) or []],
        "teams": list(slip.get("teams", []) or []),
        "justification": slip.get("justification", ""),
        "risk_warning": _risk_warning(slip),
    }


def _risk_warning(slip: Mapping[str, Any]) -> str:
    confidence = _mapping(slip.get("confidence"))
    grade = str(confidence.get("grade", slip.get("confidence_grade", "")))
    if grade in {"Low", "Very Low"}:
        return f"Confidence warning: {grade} slip."
    justification = str(slip.get("justification", ""))
    if "Confidence warning:" in justification:
        return justification.split("Confidence warning:", 1)[1].strip()
    return ""


def _slip_group(raw: str) -> str:
    normalized = raw.replace("_slips", "").replace("_", " ").strip().lower()
    if "non superstar" in normalized or "non-superstar" in normalized:
        return "Non-Superstar Core"
    if "balanced" in normalized:
        return "Balanced"
    if "chaos" in normalized:
        return "Chaos"
    if "contrarian" in normalized:
        return "Contrarian"
    return "Core"


def _confidence_label(row: Mapping[str, Any]) -> str:
    grade = row.get("confidence_grade") or row.get("grade", "")
    score = row.get("confidence_score") or row.get("score", "")
    return f"{grade} {score}".strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _display(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return str(value)


def _message(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("message", value))
    return str(value)


def _found(value: Any) -> str:
    return "Found" if value else "Missing"


def _accuracy_bucket_rows(values: Any) -> list[dict[str, Any]]:
    rows = []
    for item in values or []:
        row = _mapping(item)
        rows.append(
            {
                "Group": row.get("label", ""),
                "Appearances": row.get("appearances", 0),
                "Hits": row.get("hits", 0),
                "Misses": row.get("misses", 0),
                "Hit Rate": _percent(row.get("hit_rate", 0.0)),
            }
        )
    return rows


def _percent(value: Any) -> str:
    try:
        return f"{float(value or 0.0):.1%}"
    except (TypeError, ValueError):
        return "0.0%"
