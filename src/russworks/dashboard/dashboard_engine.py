from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from russworks.backtesting import BacktestResult, DailyBacktestSummary
from russworks.calibration import CalibrationMetric, CalibrationResult
from russworks.confidence import ConfidenceEngine, ConfidenceResult
from russworks.diversification import DiversificationResult
from russworks.integrity import IntegrityReport
from russworks.portfolio import PortfolioProfile
from russworks.postmortem import PostMortemReport
from russworks.self_learning import SelfLearningReport
from russworks.simulation import SimulationResult

from .dashboard_models import (
    ArchetypePerformance,
    CalibrationDashboard,
    ModulePerformance,
    TrendReport,
)


if TYPE_CHECKING:
    from russworks.scheduler import SchedulerStatus


_DISPLAY_NAMES = {
    "Pitch Mix": "Pitch Mix Matchup",
    "Park Factor": "Park Factor V2",
}


_MODULE_ORDER = [
    "TAG",
    "CPS",
    "LSTM",
    "Environment",
    "Umpire",
    "PVS",
    "Weak Spot Collision",
    "YPI",
    "Veteran Bounce",
    "Catcher Power",
    "Pitch Mix Matchup",
    "Bullpen Exposure",
    "Park Factor V2",
]


_OPERATIONS_KEYS = [
    "last_slate_run",
    "last_postmortem_run",
    "last_successful_acquisition",
    "hr_events_acquired",
    "winners",
    "misses",
    "false_positives",
    "adjustments",
    "calibration_recommendations",
]


class CalibrationDashboardEngine:
    def build_dashboard(
        self,
        *,
        calibration_result: CalibrationResult | None = None,
        postmortem_reports: Sequence[PostMortemReport] = (),
        backtest_result: BacktestResult | None = None,
        integrity_report: IntegrityReport | None = None,
        confidence_results: Sequence[ConfidenceResult] = (),
        portfolio_profile: PortfolioProfile | None = None,
        diversification_result: DiversificationResult | None = None,
        simulation_result: SimulationResult | None = None,
        self_learning_report: SelfLearningReport | None = None,
        scheduler_status: SchedulerStatus | None = None,
        validation_summary: dict[str, object] | None = None,
        skipped_games: Sequence[object] = (),
    ) -> CalibrationDashboard:
        modules = _module_performances(calibration_result, backtest_result)
        top = sorted(modules, key=lambda item: (item.confidence_accuracy, item.hit_rate, item.wins), reverse=True)[:5]
        worst = sorted(modules, key=lambda item: (item.confidence_accuracy, item.hit_rate, -item.false_positives))[:5]
        thirty_day = _trend_report("30-Day Trends", backtest_result, limit_days=30)
        season = _trend_report("Season Trends", backtest_result, limit_days=None)
        archetypes = _archetype_performance(postmortem_reports)
        summaries = _summaries(modules, top, worst, thirty_day, season, archetypes, calibration_result)
        integrity_summaries = _integrity_summaries(integrity_report)
        confidence_summaries = ConfidenceEngine().summarize_results(list(confidence_results))
        portfolio_summaries = _portfolio_summaries(portfolio_profile)
        diversification_summaries = _diversification_summaries(diversification_result)
        simulation_summaries = _simulation_summaries(simulation_result)
        self_learning_summaries = _self_learning_summaries(self_learning_report)
        scheduler_summaries = _scheduler_summaries(scheduler_status)
        operations_summary = _operations_summary(scheduler_status, postmortem_reports, calibration_result)
        validation_summaries = _validation_summaries(validation_summary)
        skipped_game_summaries = _skipped_game_summaries(skipped_games)
        errors = []
        if calibration_result and calibration_result.errors:
            errors.extend(calibration_result.errors)
        if backtest_result and backtest_result.errors:
            errors.extend(backtest_result.errors)
        if not modules:
            errors.append("Calibration dashboard requires calibration metrics or backtest summaries.")
        return CalibrationDashboard(
            generated_at=_now(),
            modules=modules,
            top_performing_modules=top,
            worst_performing_modules=worst,
            thirty_day_trends=thirty_day,
            season_trends=season,
            archetype_success_rates=archetypes,
            trend_summaries=summaries,
            integrity_summaries=integrity_summaries,
            confidence_summaries=confidence_summaries,
            portfolio_summaries=portfolio_summaries,
            diversification_summaries=diversification_summaries,
            simulation_summaries=simulation_summaries,
            self_learning_summaries=self_learning_summaries,
            scheduler_summaries=scheduler_summaries,
            operations_summary=operations_summary,
            validation_summaries=validation_summaries,
            skipped_game_summaries=skipped_game_summaries,
            errors=errors,
        )

    def export_json(self, dashboard: CalibrationDashboard, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / "dashboard.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard = _with_persisted_operations_summary(dashboard, output_path)
        output_path.write_text(dashboard.to_json(), encoding="utf-8")
        return output_path

    def build_weight_recommendations(
        self,
        dashboard: CalibrationDashboard,
        *,
        calibration_result: CalibrationResult | None = None,
        backtest_result: BacktestResult | None = None,
        current_weights=None,
    ):
        from russworks.recommendations import WeightRecommendationEngine

        return WeightRecommendationEngine().build_recommendations(
            calibration_result=calibration_result,
            dashboard=dashboard,
            backtest_result=backtest_result,
            current_weights=current_weights,
        )

    def build_trends(
        self,
        dashboard: CalibrationDashboard,
        *,
        calibration_result: CalibrationResult | None = None,
        recommendation_report=None,
        backtest_result: BacktestResult | None = None,
    ):
        from russworks.trends import TrendEngine

        return TrendEngine().build_trends(
            dashboard=dashboard,
            calibration_result=calibration_result,
            recommendation_report=recommendation_report,
            backtest_result=backtest_result,
        )

    def build_optimizer(
        self,
        dashboard: CalibrationDashboard,
        *,
        calibration_result: CalibrationResult | None = None,
        recommendation_report=None,
        trend_summary=None,
        backtest_result: BacktestResult | None = None,
        current_weights=None,
    ):
        from russworks.optimizer import FormulaOptimizer

        return FormulaOptimizer().optimize(
            dashboard=dashboard,
            calibration_result=calibration_result,
            recommendation_report=recommendation_report,
            trend_summary=trend_summary,
            backtest_result=backtest_result,
            current_weights=current_weights,
        )


def build_calibration_dashboard(
    calibration_result: CalibrationResult | None = None,
    *,
    postmortem_reports: Sequence[PostMortemReport] = (),
    backtest_result: BacktestResult | None = None,
    integrity_report: IntegrityReport | None = None,
    confidence_results: Sequence[ConfidenceResult] = (),
    portfolio_profile: PortfolioProfile | None = None,
    diversification_result: DiversificationResult | None = None,
    simulation_result: SimulationResult | None = None,
    self_learning_report: SelfLearningReport | None = None,
    scheduler_status: SchedulerStatus | None = None,
    validation_summary: dict[str, object] | None = None,
    skipped_games: Sequence[object] = (),
) -> CalibrationDashboard:
    return CalibrationDashboardEngine().build_dashboard(
        calibration_result=calibration_result,
        postmortem_reports=postmortem_reports,
        backtest_result=backtest_result,
        integrity_report=integrity_report,
        confidence_results=confidence_results,
        portfolio_profile=portfolio_profile,
        diversification_result=diversification_result,
        simulation_result=simulation_result,
        self_learning_report=self_learning_report,
        scheduler_status=scheduler_status,
        validation_summary=validation_summary,
        skipped_games=skipped_games,
    )


def _module_performances(
    calibration_result: CalibrationResult | None,
    backtest_result: BacktestResult | None,
) -> list[ModulePerformance]:
    by_module: dict[str, ModulePerformance] = {}
    if calibration_result:
        for metric in calibration_result.metrics:
            performance = _from_calibration_metric(metric)
            by_module[performance.module] = performance

    if backtest_result and backtest_result.summary:
        for performance in _from_backtest_summary(backtest_result):
            by_module.setdefault(performance.module, performance)

    return [by_module[module] for module in _MODULE_ORDER if module in by_module]


def _from_calibration_metric(metric: CalibrationMetric) -> ModulePerformance:
    module = _display_name(metric.module)
    losses = max(0, metric.appearances - metric.hits)
    return ModulePerformance(
        module=module,
        appearances=metric.appearances,
        wins=metric.hits,
        losses=losses,
        hit_rate=metric.hit_rate,
        false_positives=metric.false_positives,
        false_negatives=metric.false_negatives,
        confidence_accuracy=metric.confidence_score,
    )


def _from_backtest_summary(backtest_result: BacktestResult) -> list[ModulePerformance]:
    summary = backtest_result.summary
    assert summary is not None
    appearances = max(summary.total_batters_reviewed, 0)
    values = [
        ("YPI", summary.ypi_hits),
        ("Veteran Bounce", summary.veteran_hits),
        ("Catcher Power", summary.catcher_hits),
        ("Weak Spot Collision", summary.weak_spot_hits),
        ("Pitch Mix Matchup", summary.pitch_mix_hits),
    ]
    return [
        ModulePerformance(
            module=module,
            appearances=appearances,
            wins=hits,
            losses=max(0, appearances - hits),
            hit_rate=_rate(hits, appearances),
            false_positives=max(0, appearances - hits),
            false_negatives=max(0, summary.total_hrs_hit - hits),
            confidence_accuracy=_confidence(appearances, hits, max(0, appearances - hits), max(0, summary.total_hrs_hit - hits)),
        )
        for module, hits in values
    ]


def _trend_report(
    label: str,
    backtest_result: BacktestResult | None,
    *,
    limit_days: int | None,
) -> TrendReport | None:
    if backtest_result is None or not backtest_result.daily_summaries:
        return None
    summaries = list(backtest_result.daily_summaries)
    if limit_days is not None:
        summaries = summaries[-limit_days:]
    start = summaries[0].date
    end = summaries[-1].date
    module_trends = _module_trends_from_daily(summaries)
    notes = [
        f"{label}: {len(summaries)} dates included.",
        f"{label}: Step 3 hit rate {_rate(sum(item.step3_hits for item in summaries), sum(item.total_hrs_hit for item in summaries)):.1%}.",
        f"{label}: Step 5 hit rate {_rate(sum(item.step5_hits for item in summaries), sum(item.total_hrs_hit for item in summaries)):.1%}.",
    ]
    return TrendReport(label=label, start_date=start, end_date=end, module_trends=module_trends, summaries=notes)


def _module_trends_from_daily(daily_summaries: Sequence[DailyBacktestSummary]) -> list[ModulePerformance]:
    appearances = sum(item.total_batters_reviewed for item in daily_summaries)
    total_hrs = sum(item.total_hrs_hit for item in daily_summaries)
    module_hits = {
        "YPI": sum(item.ypi_hits for item in daily_summaries),
        "Veteran Bounce": sum(item.veteran_hits for item in daily_summaries),
        "Catcher Power": sum(item.catcher_hits for item in daily_summaries),
        "Weak Spot Collision": sum(item.weak_spot_hits for item in daily_summaries),
        "Pitch Mix Matchup": sum(item.pitch_mix_hits for item in daily_summaries),
    }
    return [
        ModulePerformance(
            module=module,
            appearances=appearances,
            wins=hits,
            losses=max(0, appearances - hits),
            hit_rate=_rate(hits, appearances),
            false_positives=max(0, appearances - hits),
            false_negatives=max(0, total_hrs - hits),
            confidence_accuracy=_confidence(appearances, hits, max(0, appearances - hits), max(0, total_hrs - hits)),
        )
        for module, hits in module_hits.items()
    ]


def _archetype_performance(postmortem_reports: Sequence[PostMortemReport]) -> list[ArchetypePerformance]:
    wins: Counter[str] = Counter()
    losses: Counter[str] = Counter()
    false_positives: Counter[str] = Counter()
    for report in postmortem_reports:
        for winner in report.winner_log:
            wins.update(_display_name(archetype) for archetype in winner.archetypes)
        for loser in report.loser_log:
            losses.update(_display_name(archetype) for archetype in loser.archetypes)
        for entry in report.false_positive_log:
            false_positives.update(_display_name(module) for module in entry.overweighted_modules)

    archetypes = sorted(set(wins) | set(losses) | set(false_positives))
    performances = []
    for archetype in archetypes:
        appearances = wins[archetype] + losses[archetype]
        performances.append(
            ArchetypePerformance(
                archetype=archetype,
                appearances=appearances,
                wins=wins[archetype],
                losses=losses[archetype],
                hit_rate=_rate(wins[archetype], appearances),
                false_positives=false_positives[archetype],
                confidence_accuracy=_confidence(appearances, wins[archetype], false_positives[archetype], 0),
            )
        )
    return sorted(performances, key=lambda item: (item.hit_rate, item.wins), reverse=True)


def _summaries(
    modules: Sequence[ModulePerformance],
    top: Sequence[ModulePerformance],
    worst: Sequence[ModulePerformance],
    thirty_day: TrendReport | None,
    season: TrendReport | None,
    archetypes: Sequence[ArchetypePerformance],
    calibration_result: CalibrationResult | None,
) -> list[str]:
    summaries = []
    if top:
        summaries.append(f"Top Performing Module: {top[0].module} at {top[0].hit_rate:.1%}.")
    if worst:
        summaries.append(f"Worst Performing Module: {worst[0].module} with {worst[0].false_positives} false positives.")
    if thirty_day:
        summaries.extend(thirty_day.summaries)
    if season:
        summaries.extend(season.summaries)
    if archetypes:
        summaries.append(f"Top Archetype: {archetypes[0].archetype} at {archetypes[0].hit_rate:.1%}.")
    if calibration_result:
        summaries.extend(calibration_result.trend_summaries)
    if not summaries and modules:
        summaries.append("Dashboard generated from module performance metrics.")
    return summaries


def _display_name(module: str) -> str:
    return _DISPLAY_NAMES.get(module, module)


def _integrity_summaries(report: IntegrityReport | None) -> list[str]:
    if report is None:
        return []
    counts = report.severity_counts
    total = sum(counts.values())
    if total == 0:
        return ["Data integrity monitor found no alerts."]
    return [
        "Data integrity alerts: "
        + ", ".join(f"{severity}={count}" for severity, count in counts.items() if count)
        + "."
    ]


def _portfolio_summaries(profile: PortfolioProfile | None) -> list[str]:
    if profile is None:
        return []
    return [
        f"Portfolio risk {profile.risk_report.risk_grade.value} at {profile.risk_report.risk_score:.1f}.",
        f"Portfolio recommendations generated: {len(profile.recommendations)}.",
    ]


def _diversification_summaries(result: DiversificationResult | None) -> list[str]:
    if result is None:
        return []
    return [
        f"Diversification target {result.target.value} generated {len(result.recommendations)} recommendations.",
        f"Suggested swaps: {len(result.suggested_swaps)}.",
    ]


def _simulation_summaries(result: SimulationResult | None) -> list[str]:
    if result is None or result.summary is None:
        return []
    return [
        f"Monte Carlo simulations: {result.summary.simulation_count}.",
        f"Expected hit rate {result.summary.expected_hit_rate:.1%}, expected ROI {result.summary.expected_roi:.1%}.",
        f"Simulation risk grade {result.summary.risk_grade.value}.",
    ]


def _self_learning_summaries(report: SelfLearningReport | None) -> list[str]:
    if report is None:
        return []
    return [
        f"Self-learning observations: {len(report.observations)}.",
        f"Self-learning recommendations: {len(report.recommendations)}.",
        f"Top self-learning modules: {', '.join(report.summary.top_performing_modules[:3]) if report.summary.top_performing_modules else 'none'}.",
    ]


def _scheduler_summaries(status: SchedulerStatus | None) -> list[str]:
    if status is None:
        return []
    failed = len([task for task in status.tasks if task.status.value == "failed"])
    return [
        f"Scheduler tasks tracked: {len(status.tasks)}.",
        f"Scheduler failed tasks: {failed}.",
        f"Scheduler status: {'success' if status.success else 'attention required'}.",
    ]


def _operations_summary(
    status: SchedulerStatus | None,
    postmortem_reports: Sequence[PostMortemReport],
    calibration_result: CalibrationResult | None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "last_slate_run": "",
        "last_postmortem_run": "",
        "last_successful_acquisition": "",
        "hr_events_acquired": sum(len(report.actual_home_runs) for report in postmortem_reports),
        "winners": sum(len(report.winner_log) for report in postmortem_reports),
        "misses": sum(len(report.loser_log) for report in postmortem_reports),
        "false_positives": sum(len(report.false_positive_log) for report in postmortem_reports),
        "adjustments": sum(len(report.adjustment_log) for report in postmortem_reports),
        "calibration_recommendations": len(calibration_result.recommended_adjustments) if calibration_result else 0,
    }
    if status is None:
        return summary

    for item in [*getattr(status, "history", []), *getattr(status, "tasks", [])]:
        metadata = getattr(item, "metadata", {}) or {}
        generated_at = getattr(item, "generated_at", "") or getattr(item, "finished_at", "") or getattr(item, "last_run", "")
        if metadata.get("last_slate_run") or metadata.get("slate_output_dir"):
            summary["last_slate_run"] = metadata.get("last_slate_run") or generated_at
        if metadata.get("last_postmortem_run"):
            summary["last_postmortem_run"] = metadata.get("last_postmortem_run")
        if metadata.get("last_successful_acquisition"):
            summary["last_successful_acquisition"] = metadata.get("last_successful_acquisition")
        for key in ["hr_events_acquired", "winners", "misses", "false_positives", "adjustments", "calibration_recommendations"]:
            value = metadata.get(key)
            if isinstance(value, (int, float)) and value:
                summary[key] = int(value)
    return summary


def _with_persisted_operations_summary(dashboard: CalibrationDashboard, output_path: Path) -> CalibrationDashboard:
    data_root = output_path.parent.parent
    merged = _merge_operations_summaries(
        _empty_operations_summary(),
        _existing_dashboard_operations(output_path),
        _scheduler_history_operations(data_root),
        _latest_postmortem_operations(data_root),
        dashboard.operations_summary,
    )
    if merged == dashboard.operations_summary:
        return dashboard
    return replace(dashboard, operations_summary=merged)


def _empty_operations_summary() -> dict[str, object]:
    return {
        "last_slate_run": "",
        "last_postmortem_run": "",
        "last_successful_acquisition": "",
        "hr_events_acquired": 0,
        "winners": 0,
        "misses": 0,
        "false_positives": 0,
        "adjustments": 0,
        "calibration_recommendations": 0,
    }


def _existing_dashboard_operations(path: Path) -> dict[str, object]:
    payload = _read_json(path)
    return _operations_from_mapping(_mapping(payload.get("operations_summary")))


def _scheduler_history_operations(data_root: Path) -> dict[str, object]:
    history = _read_json_list(data_root / "scheduler" / "run_history.json")
    merged = _empty_operations_summary()
    for entry in history:
        metadata = _mapping(entry.get("metadata"))
        generated_at = str(entry.get("generated_at", ""))
        merged = _merge_operations_summaries(merged, _operations_from_metadata(metadata, generated_at))
    return merged


def _latest_postmortem_operations(data_root: Path) -> dict[str, object]:
    postmortem_root = data_root / "postmortem"
    if not postmortem_root.exists():
        return {}
    date_dirs = sorted([path for path in postmortem_root.iterdir() if path.is_dir()], key=lambda item: item.stat().st_mtime)
    merged = _empty_operations_summary()
    for date_dir in date_dirs:
        merged = _merge_operations_summaries(merged, _postmortem_directory_operations(date_dir))
    return merged


def _postmortem_directory_operations(date_dir: Path) -> dict[str, object]:
    metadata = _read_json(date_dir / "run_metadata.json")
    report = _read_json(date_dir / "postmortem_report.json")
    calibration = _read_json(date_dir / "calibration_result.json")
    generated_at = str(metadata.get("executed_at") or _mtime_text(date_dir / "run_metadata.json") or _mtime_text(date_dir / "postmortem_report.json"))
    summary = _operations_from_metadata(_mapping(metadata), generated_at)
    if report:
        summary = _merge_operations_summaries(summary, _operations_from_postmortem_report(report))
    if calibration:
        summary = _merge_operations_summaries(summary, _operations_from_calibration(calibration))
    return summary


def _operations_from_metadata(metadata: Mapping[str, Any], generated_at: str = "") -> dict[str, object]:
    return {
        "last_slate_run": metadata.get("last_slate_run", ""),
        "last_postmortem_run": metadata.get("last_postmortem_run") or generated_at,
        "last_successful_acquisition": metadata.get("last_successful_acquisition") or (generated_at if _int_value(metadata.get("actual_home_runs_loaded") or metadata.get("hr_events_acquired")) else ""),
        "hr_events_acquired": _int_value(metadata.get("hr_events_acquired") or metadata.get("actual_home_runs_loaded")),
        "winners": _int_value(metadata.get("winners")),
        "misses": _int_value(metadata.get("misses")),
        "false_positives": _int_value(metadata.get("false_positives")),
        "adjustments": _int_value(metadata.get("adjustments")),
        "calibration_recommendations": _int_value(metadata.get("calibration_recommendations")),
    }


def _operations_from_postmortem_report(report: Mapping[str, Any]) -> dict[str, object]:
    return {
        "winners": len(report.get("winner_log", []) or []),
        "misses": len(report.get("loser_log", []) or []),
        "false_positives": len(report.get("false_positive_log", []) or []),
        "adjustments": len(report.get("adjustment_log", []) or []),
        "hr_events_acquired": len(report.get("actual_home_runs", []) or []),
    }


def _operations_from_calibration(calibration: Mapping[str, Any]) -> dict[str, object]:
    return {
        "calibration_recommendations": len(calibration.get("recommended_adjustments", []) or []),
    }


def _operations_from_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    return {key: value.get(key, _empty_operations_summary()[key]) for key in _OPERATIONS_KEYS}


def _merge_operations_summaries(*summaries: Mapping[str, Any]) -> dict[str, object]:
    merged = _empty_operations_summary()
    for summary in summaries:
        for key in _OPERATIONS_KEYS:
            value = summary.get(key)
            if _meaningful_operation_value(value):
                merged[key] = value
    return merged


def _meaningful_operation_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mtime_text(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.utcfromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat() + "Z"


def _validation_summaries(summary: dict[str, object] | None) -> list[str]:
    if not summary:
        return []
    return [
        "Slate validation: "
        + ", ".join(
            f"{key}={summary.get(key)}"
            for key in ("total_games", "complete_games", "incomplete_games", "skipped_games", "park_factor_fallback_games")
            if key in summary
        )
        + "."
    ]


def _skipped_game_summaries(skipped_games: Sequence[object]) -> list[str]:
    summaries = []
    for game in skipped_games:
        game_id = getattr(game, "game_id", "")
        reasons = getattr(game, "skipped_reason", [])
        summaries.append(f"Skipped {game_id}: {'; '.join(str(reason) for reason in reasons)}")
    return summaries


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _confidence(appearances: int, wins: int, false_positives: int, false_negatives: int) -> float:
    if appearances <= 0:
        return 0.0
    precision = _rate(wins, appearances)
    penalty = min(0.35, (false_positives + false_negatives) / max(appearances + false_negatives, 1) * 0.35)
    sample = min(1.0, appearances / 20.0)
    return round(max(0.0, min(1.0, sample * 0.45 + precision * 0.55 - penalty)), 4)


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
