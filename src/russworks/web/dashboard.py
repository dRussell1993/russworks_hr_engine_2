from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from russworks.command_center import CommandCenterReport
from russworks.dashboard import CalibrationDashboard
from russworks.reports import FullRussWorksReport, load_full_report_payload
from russworks.scheduler import SchedulerStatus

from .models import (
    BatterView,
    DashboardView,
    PortfolioView,
    SchedulerView,
    SimulationView,
    SlipView,
    TeamView,
)


class OperatorDashboardBuilder:
    def build_dashboard(
        self,
        *,
        report: FullRussWorksReport | Mapping[str, Any] | None = None,
        dashboard: CalibrationDashboard | Mapping[str, Any] | None = None,
        command_center: CommandCenterReport | Mapping[str, Any] | None = None,
        scheduler_status: SchedulerStatus | Mapping[str, Any] | None = None,
        explanations: Mapping[str, Any] | None = None,
    ) -> DashboardView:
        report_payload = _report_payload(report)
        dashboard_payload = _payload(dashboard)
        command_payload = _payload(command_center)
        scheduler_payload = _payload(scheduler_status)
        explanation_payload = dict(explanations or report_payload.get("explanations", {}) or {})
        return DashboardView(
            generated_at=_now(),
            metadata=_metadata(report_payload),
            batters=_batter_views(report_payload),
            teams=_team_views(report_payload),
            slips=_slip_views(report_payload),
            portfolio=_portfolio_view(report_payload),
            simulation=_simulation_view(report_payload),
            scheduler=_scheduler_view(scheduler_payload),
            provider_health=_provider_health(command_payload),
            confidence_views=_confidence_views(report_payload, command_payload),
            explanations=explanation_payload,
            command_center=command_payload,
            dashboard_summary=dashboard_payload,
            errors=_errors(report_payload, command_payload, scheduler_payload),
        )

    def build_from_report_file(
        self,
        report_path: str | Path,
        *,
        dashboard_path: str | Path | None = None,
        command_center_path: str | Path | None = None,
        scheduler_path: str | Path | None = None,
    ) -> DashboardView:
        report_payload = load_full_report_payload(_load_json(report_path))
        return self.build_dashboard(
            report=report_payload,
            dashboard=_load_json(dashboard_path) if dashboard_path else None,
            command_center=_load_json(command_center_path) if command_center_path else None,
            scheduler_status=_load_json(scheduler_path) if scheduler_path else None,
        )

    def export_json(self, view: DashboardView, output_dir: str | Path = "data/web") -> Path:
        output_path = Path(output_dir) / "dashboard_data.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(view.to_json(), encoding="utf-8")
        return output_path


def build_dashboard_view(**kwargs: Any) -> DashboardView:
    return OperatorDashboardBuilder().build_dashboard(**kwargs)


def export_dashboard_data(view: DashboardView, output_dir: str | Path = "data/web") -> Path:
    return OperatorDashboardBuilder().export_json(view, output_dir)


def _report_payload(report: FullRussWorksReport | Mapping[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {}
    if isinstance(report, FullRussWorksReport):
        return report.to_dict()
    return dict(report)


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return _json_ready(dict(value))
    return {}


def _metadata(report: Mapping[str, Any]) -> dict[str, Any]:
    context = _mapping(report.get("context"))
    return {
        "report_date": context.get("report_date", ""),
        "games_reviewed": context.get("games_reviewed", 0),
        "validation_status": context.get("validation_status", ""),
        "schema_version": report.get("schema_version", ""),
        "game_ids": list(context.get("game_ids", []) or []),
    }


def _batter_views(report: Mapping[str, Any]) -> list[BatterView]:
    rows = list(_mapping(report.get("step3")).get("batter_reviews", []) or [])
    rows.sort(key=lambda item: float(item.get("russ_score", 0.0) or 0.0), reverse=True)
    return [
        BatterView(
            rank=index,
            batter=str(row.get("batter", "")),
            team=str(row.get("team", "")),
            opponent=str(row.get("opponent", "")),
            lineup_slot=int(row.get("lineup_slot", 0) or 0),
            russ_score=float(row.get("russ_score", 0.0) or 0.0),
            tier=str(row.get("tier", "")),
            confidence_score=float(_mapping(row.get("confidence")).get("score", 0.0) or 0.0),
            confidence_grade=str(_mapping(row.get("confidence")).get("grade", "")),
            key_factors=_key_factors(row),
        )
        for index, row in enumerate(rows, start=1)
    ]


def _team_views(report: Mapping[str, Any]) -> list[TeamView]:
    rows = list(_mapping(report.get("step4")).get("team_rankings", []) or [])
    return [
        TeamView(
            rank=int(row.get("rank", index) or index),
            team=str(row.get("team", "")),
            opponent=str(row.get("opponent", "")),
            tag_grade=str(row.get("tag_grade", "")),
            cps_grade=str(row.get("cps_grade", "")),
            total_cluster_score=float(row.get("total_cluster_score", 0.0) or 0.0),
            cluster_strength_label=str(row.get("cluster_strength_label", "")),
            cluster_captain=str(row.get("cluster_captain", "")),
            hidden_cluster_beneficiary=str(row.get("hidden_cluster_beneficiary", "")),
            confidence_grade=str(_mapping(row.get("confidence")).get("grade", "")),
        )
        for index, row in enumerate(rows, start=1)
    ]


def _slip_views(report: Mapping[str, Any]) -> list[SlipView]:
    step5 = _mapping(report.get("step5"))
    slips: list[dict[str, Any]] = []
    for key in ["core_slips", "non_superstar_core_slips", "balanced_slips", "chaos_slips", "contrarian_slips"]:
        slips.extend(dict(row, slip_bucket=key) for row in step5.get(key, []) or [])
    return [
        SlipView(
            name=str(row.get("name", "")),
            slip_type=str(row.get("slip_type", row.get("slip_bucket", ""))),
            confidence_score=float(_mapping(row.get("confidence")).get("score", 0.0) or 0.0),
            confidence_grade=str(_mapping(row.get("confidence")).get("grade", "")),
            batters=[str(leg.get("batter", "")) for leg in row.get("legs", [])],
            teams=sorted({str(leg.get("team", "")) for leg in row.get("legs", []) if leg.get("team")}),
            justification=str(row.get("justification", "")),
        )
        for row in slips
    ]


def _portfolio_view(report: Mapping[str, Any]) -> PortfolioView:
    portfolio = _mapping(report.get("portfolio"))
    risk = _mapping(portfolio.get("risk_report"))
    exposure = _mapping(portfolio.get("exposure_report"))
    diversification = _mapping(report.get("diversification"))
    return PortfolioView(
        risk_grade=str(risk.get("risk_grade", "")),
        risk_score=float(risk.get("risk_score", 0.0) or 0.0),
        team_exposure=_float_map(exposure.get("team_exposure")),
        game_exposure=_float_map(exposure.get("game_exposure")),
        confidence_exposure=_float_map(exposure.get("confidence_exposure")),
        recommendations=[str(item.get("message", item)) for item in portfolio.get("recommendations", [])],
        diversification_recommendations=[
            str(item.get("message", item))
            for item in diversification.get("recommendations", [])
        ],
    )


def _simulation_view(report: Mapping[str, Any]) -> SimulationView:
    summary = _mapping(_mapping(report.get("simulation")).get("summary"))
    return SimulationView(
        simulation_count=int(summary.get("simulation_count", 0) or 0),
        expected_hit_rate=float(summary.get("expected_hit_rate", 0.0) or 0.0),
        expected_roi=float(summary.get("expected_roi", 0.0) or 0.0),
        expected_variance=float(summary.get("expected_variance", 0.0) or 0.0),
        drawdown_risk=float(summary.get("drawdown_risk", 0.0) or 0.0),
        portfolio_volatility=float(summary.get("portfolio_volatility", 0.0) or 0.0),
        risk_grade=str(summary.get("risk_grade", "")),
        confidence_intervals=_mapping(summary.get("confidence_intervals")),
    )


def _scheduler_view(status: Mapping[str, Any]) -> SchedulerView:
    tasks = list(status.get("tasks", []) or [])
    counts: dict[str, int] = {}
    for task in tasks:
        task_status = str(task.get("status", ""))
        counts[task_status] = counts.get(task_status, 0) + 1
    return SchedulerView(
        generated_at=str(status.get("generated_at", "")),
        success=bool(status.get("success", not status.get("errors"))),
        task_status_counts=counts,
        tasks=tasks,
    )


def _provider_health(command_center: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(_mapping(command_center.get("slate_status")).get("provider_health", []) or [])


def _confidence_views(report: Mapping[str, Any], command_center: Mapping[str, Any]) -> dict[str, Any]:
    batter_rows = _mapping(report.get("step3")).get("batter_reviews", []) or []
    grade_counts: dict[str, int] = {}
    for row in batter_rows:
        grade = str(_mapping(row.get("confidence")).get("grade", ""))
        if grade:
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
    return {
        "batter_confidence_grade_counts": grade_counts,
        "command_center_confidence": _mapping(_mapping(command_center.get("formula_health")).get("confidence_summary")),
    }


def _errors(*payloads: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for payload in payloads:
        for error in payload.get("errors", []) or []:
            errors.append(str(error))
    return errors


def _key_factors(row: Mapping[str, Any]) -> list[str]:
    factors = []
    for key in ["weak_spot_collision", "ypi", "veteran_bounce", "catcher_power"]:
        data = _mapping(row.get(key))
        if data.get("flag"):
            factors.append(key)
    if row.get("non_superstar_core"):
        factors.append("non_superstar_core")
    return factors


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): float(item or 0.0) for key, item in value.items()}


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
