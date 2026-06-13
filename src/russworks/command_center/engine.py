from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from russworks.config.weights import ScoringWeights
from russworks.dashboard import CalibrationDashboard
from russworks.data import DailySlate
from russworks.integrity import IntegrityReport
from russworks.intake import validate_step2_intake
from russworks.optimizer import OptimizationResult
from russworks.pipeline import DailyRunResult
from russworks.providers import ProviderHealth
from russworks.recommendations import RecommendationReport
from russworks.trends import TrendSummary

from .models import CommandCenterReport, DailyExecutionSummary, DailySlateStatus, FormulaHealthReport


class CommandCenterEngine:
    def build_report(
        self,
        *,
        date: str = "",
        daily_run_result: DailyRunResult | None = None,
        slate: DailySlate | None = None,
        dashboard: CalibrationDashboard | None = None,
        recommendations: RecommendationReport | None = None,
        trends: TrendSummary | None = None,
        optimizer: OptimizationResult | None = None,
        integrity_report: IntegrityReport | None = None,
        provider_health: Iterable[ProviderHealth | Mapping[str, Any]] = (),
        weights: ScoringWeights | Mapping[str, Any] | None = None,
        explanations_path: str = "",
    ) -> CommandCenterReport:
        active_slate = slate or (daily_run_result.slate if daily_run_result else None)
        report_date = date or _date_from_inputs(daily_run_result, active_slate)
        slate_status = self.daily_slate_status(
            report_date,
            active_slate,
            daily_run_result=daily_run_result,
            provider_health=provider_health,
            integrity_report=integrity_report,
        )
        formula_health = self.formula_health(
            weights=weights,
            dashboard=dashboard,
            recommendations=recommendations,
            trends=trends,
            optimizer=optimizer,
            daily_run_result=daily_run_result,
        )
        execution_summary = self.execution_summary(
            daily_run_result=daily_run_result,
            dashboard=dashboard,
            recommendations=recommendations,
            trends=trends,
            optimizer=optimizer,
            integrity_report=integrity_report,
            explanations_path=explanations_path,
        )
        errors = list(execution_summary.errors)
        warnings = list(execution_summary.warnings)
        if slate_status.validation_failures:
            errors.append("Step 2 validation failures are present in the daily slate.")
        if slate_status.integrity_alerts.get("ERROR", 0) or slate_status.integrity_alerts.get("CRITICAL", 0):
            errors.append("Data integrity errors are present in the daily slate.")
        if active_slate is None:
            warnings.append("No daily slate was provided to the command center.")
        return CommandCenterReport(
            generated_at=_now(),
            slate_status=slate_status,
            formula_health=formula_health,
            execution_summary=execution_summary,
            explanations_path=explanations_path,
            errors=errors,
            warnings=warnings,
        )

    def daily_slate_status(
        self,
        date: str,
        slate: DailySlate | None,
        *,
        daily_run_result: DailyRunResult | None = None,
        provider_health: Iterable[ProviderHealth | Mapping[str, Any]] = (),
        integrity_report: IntegrityReport | None = None,
    ) -> DailySlateStatus:
        active_integrity = integrity_report or (daily_run_result.integrity_report if daily_run_result else None)
        if slate is None:
            missing = dict(daily_run_result.missing_data) if daily_run_result else {}
            return DailySlateStatus(
                date=date,
                games_loaded=0,
                batters_loaded=0,
                confirmed_lineups=0,
                missing_lineups=_missing_lineup_messages(missing),
                provider_health=[*_provider_health_rows(provider_health)],
                validation_failures=missing,
                integrity_alerts=_integrity_counts(active_integrity),
            )

        validation_failures = _validation_failures(slate)
        provider_rows = [*_provider_health_rows(provider_health), *_provider_health_from_metadata(slate.metadata)]
        return DailySlateStatus(
            date=date or slate.date,
            games_loaded=slate.total_games,
            batters_loaded=sum(len(team.batters) for game in slate.games for team in game.teams),
            confirmed_lineups=sum(1 for game in slate.games for team in game.teams if _team_lineup_confirmed(team.batters)),
            missing_lineups=_missing_lineup_messages(validation_failures),
            provider_health=provider_rows,
            validation_failures=validation_failures,
            integrity_alerts=_integrity_counts(active_integrity),
        )

    def formula_health(
        self,
        *,
        weights: ScoringWeights | Mapping[str, Any] | None = None,
        dashboard: CalibrationDashboard | None = None,
        recommendations: RecommendationReport | None = None,
        trends: TrendSummary | None = None,
        optimizer: OptimizationResult | None = None,
        daily_run_result: DailyRunResult | None = None,
    ) -> FormulaHealthReport:
        return FormulaHealthReport(
            current_module_weights=_weights_to_dict(weights),
            top_performing_modules=[item.module for item in (dashboard.top_performing_modules if dashboard else [])],
            worst_performing_modules=[item.module for item in (dashboard.worst_performing_modules if dashboard else [])],
            modules_heating_up=list(trends.heating_up if trends else []),
            modules_cooling_off=list(trends.cooling_off if trends else []),
            optimizer_recommendations=_optimizer_recommendations(optimizer, recommendations),
            confidence_summary=_confidence_summary(daily_run_result),
        )

    def execution_summary(
        self,
        *,
        daily_run_result: DailyRunResult | None = None,
        dashboard: CalibrationDashboard | None = None,
        recommendations: RecommendationReport | None = None,
        trends: TrendSummary | None = None,
        optimizer: OptimizationResult | None = None,
        integrity_report: IntegrityReport | None = None,
        explanations_path: str = "",
    ) -> DailyExecutionSummary:
        errors = list(daily_run_result.errors if daily_run_result else [])
        warnings: list[str] = []
        if dashboard and dashboard.errors:
            warnings.extend(f"dashboard: {error}" for error in dashboard.errors)
        if recommendations and recommendations.errors:
            warnings.extend(f"recommendations: {error}" for error in recommendations.errors)
        if trends and trends.errors:
            warnings.extend(f"trends: {error}" for error in trends.errors)
        if optimizer and optimizer.errors:
            warnings.extend(f"optimizer: {error}" for error in optimizer.errors)
        active_integrity = integrity_report or (daily_run_result.integrity_report if daily_run_result else None)
        if active_integrity and not active_integrity.success:
            warnings.append("integrity: data integrity report contains blocking alerts.")

        return DailyExecutionSummary(
            step2_status=_step2_status(daily_run_result),
            step3_status=_step_status(daily_run_result.step3_result if daily_run_result else None),
            step4_status=_step_status(daily_run_result.step4_result if daily_run_result else None),
            step5_status=_step_status(daily_run_result.step5_result if daily_run_result else None),
            reports_generated=_reports_generated(daily_run_result),
            exports_generated=_exports_generated(daily_run_result, dashboard, recommendations, trends, optimizer, active_integrity, explanations_path),
            integrity_report_path=_integrity_path(daily_run_result, active_integrity),
            errors=errors,
            warnings=warnings,
        )

    def export_json(self, report: CommandCenterReport, output_dir: str | Path = "data/command_center") -> Path:
        output_path = Path(output_dir) / "command_center.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.to_json(), encoding="utf-8")
        return output_path


def build_command_center_report(**kwargs: Any) -> CommandCenterReport:
    return CommandCenterEngine().build_report(**kwargs)


def _date_from_inputs(daily_run_result: DailyRunResult | None, slate: DailySlate | None) -> str:
    if daily_run_result:
        return daily_run_result.request.date
    if slate:
        return slate.date
    return ""


def _validation_failures(slate: DailySlate) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for game in slate.games:
        queue = validate_step2_intake(game)
        for category, values in queue.missing_data.items():
            merged.setdefault(category, [])
            for value in values:
                if value not in merged[category]:
                    merged[category].append(value)
    return {category: values for category, values in merged.items() if values}


def _team_lineup_confirmed(batters: Iterable[Any]) -> bool:
    slots = set()
    for batter in batters:
        if not getattr(batter, "confirmed", False):
            return False
        slot = getattr(batter, "lineup_slot", None)
        if not isinstance(slot, int) or isinstance(slot, bool) or slot < 1 or slot > 9:
            return False
        slots.add(slot)
    return slots == set(range(1, 10))


def _missing_lineup_messages(validation_failures: Mapping[str, list[str]]) -> list[str]:
    messages: list[str] = []
    for category in ("lineup", "missing_lineup_slot", "lineup_position", "invalid_lineup_position", "duplicate_lineup_slot"):
        messages.extend(validation_failures.get(category, []))
    return messages


def _provider_health_rows(provider_health: Iterable[ProviderHealth | Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in provider_health:
        if is_dataclass(item):
            rows.append(_json_ready(asdict(item)))
        elif isinstance(item, Mapping):
            rows.append(_json_ready(dict(item)))
    return rows


def _provider_health_from_metadata(metadata: Mapping[str, str]) -> list[dict[str, Any]]:
    raw = metadata.get("provider_statuses", "")
    rows = []
    for item in raw.split(","):
        if not item.strip() or ":" not in item:
            continue
        provider, status = item.split(":", 1)
        rows.append({"provider": provider, "status": status})
    if metadata.get("provider_errors"):
        rows.append({"provider": "provider_errors", "status": "error", "errors": metadata["provider_errors"]})
    return rows


def _weights_to_dict(weights: ScoringWeights | Mapping[str, Any] | None) -> dict[str, Any]:
    if weights is None:
        weights = ScoringWeights.defaults()
    if isinstance(weights, ScoringWeights):
        return {
            "tag": dict(weights.tag),
            "cps": dict(weights.cps),
            "lstm": dict(weights.lstm),
            "environment": dict(weights.environment),
            "umpire": dict(weights.umpire),
            "pvs": dict(weights.pvs),
        }
    return _json_ready(dict(weights))


def _optimizer_recommendations(
    optimizer: OptimizationResult | None,
    recommendations: RecommendationReport | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if optimizer:
        for scenario in optimizer.scenarios:
            if scenario.rejected:
                continue
            rows.append(
                {
                    "module": scenario.module,
                    "recommendation": scenario.recommendation,
                    "current_weight": scenario.current_weight,
                    "simulated_weight": scenario.simulated_weight,
                    "confidence": scenario.confidence_level,
                    "reasoning": scenario.reasoning,
                }
            )
    if rows:
        return rows
    if recommendations:
        for item in recommendations.modules:
            rows.append(
                {
                    "module": item.module,
                    "recommendation": item.trend_direction,
                    "current_weight": item.current_weight,
                    "suggested_weight": item.suggested_weight,
                    "confidence": item.confidence,
                    "reasoning": item.reasoning,
                }
            )
    return rows


def _step2_status(daily_run_result: DailyRunResult | None) -> str:
    if daily_run_result is None:
        return "not_run"
    return daily_run_result.validation_status


def _step_status(value: Any) -> str:
    if value is None:
        return "not_run"
    if getattr(value, "success", None) is False:
        return "failed"
    if getattr(value, "errors", None):
        return "failed"
    return "complete"


def _reports_generated(daily_run_result: DailyRunResult | None) -> list[str]:
    if daily_run_result is None:
        return []
    reports = []
    if daily_run_result.full_report is not None:
        reports.append("full_report")
    if daily_run_result.report_json_path:
        reports.append(daily_run_result.report_json_path)
    return reports


def _exports_generated(
    daily_run_result: DailyRunResult | None,
    dashboard: CalibrationDashboard | None,
    recommendations: RecommendationReport | None,
    trends: TrendSummary | None,
    optimizer: OptimizationResult | None,
    integrity_report: IntegrityReport | None,
    explanations_path: str = "",
) -> list[str]:
    exports = []
    if daily_run_result and daily_run_result.report_json_path:
        exports.append(daily_run_result.report_json_path)
    if dashboard:
        exports.append("data/dashboard/dashboard.json")
    if recommendations:
        exports.append("data/recommendations/recommendations.json")
    if trends:
        exports.append("data/trends/trends.json")
    if optimizer:
        exports.append("data/optimizer/optimizer_report.json")
    if daily_run_result and daily_run_result.integrity_report_path:
        exports.append(daily_run_result.integrity_report_path)
    elif integrity_report:
        exports.append("data/integrity/integrity_report.json")
    if explanations_path:
        exports.append(explanations_path)
    return exports


def _integrity_counts(report: IntegrityReport | None) -> dict[str, int]:
    return dict(report.severity_counts) if report else {}


def _integrity_path(daily_run_result: DailyRunResult | None, integrity_report: IntegrityReport | None) -> str:
    if daily_run_result and daily_run_result.integrity_report_path:
        return daily_run_result.integrity_report_path
    if integrity_report:
        return "data/integrity/integrity_report.json"
    return ""


def _confidence_summary(daily_run_result: DailyRunResult | None) -> dict[str, Any]:
    if daily_run_result is None or daily_run_result.step3_result is None:
        return {}
    reviews = list(daily_run_result.step3_result.reviews)
    if not reviews:
        return {}
    scores = [review.confidence_score for review in reviews]
    grade_counts: dict[str, int] = {}
    for review in reviews:
        grade_counts[review.confidence_grade] = grade_counts.get(review.confidence_grade, 0) + 1
    return {
        "average_confidence": round(sum(scores) / len(scores), 1),
        "min_confidence": min(scores),
        "max_confidence": max(scores),
        "grade_counts": grade_counts,
    }


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
