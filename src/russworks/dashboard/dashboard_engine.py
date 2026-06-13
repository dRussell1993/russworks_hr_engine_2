from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from russworks.backtesting import BacktestResult, DailyBacktestSummary
from russworks.calibration import CalibrationMetric, CalibrationResult
from russworks.confidence import ConfidenceEngine, ConfidenceResult
from russworks.integrity import IntegrityReport
from russworks.postmortem import PostMortemReport

from .dashboard_models import (
    ArchetypePerformance,
    CalibrationDashboard,
    ModulePerformance,
    TrendReport,
)


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


class CalibrationDashboardEngine:
    def build_dashboard(
        self,
        *,
        calibration_result: CalibrationResult | None = None,
        postmortem_reports: Sequence[PostMortemReport] = (),
        backtest_result: BacktestResult | None = None,
        integrity_report: IntegrityReport | None = None,
        confidence_results: Sequence[ConfidenceResult] = (),
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
            errors=errors,
        )

    def export_json(self, dashboard: CalibrationDashboard, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / "dashboard.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
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
) -> CalibrationDashboard:
    return CalibrationDashboardEngine().build_dashboard(
        calibration_result=calibration_result,
        postmortem_reports=postmortem_reports,
        backtest_result=backtest_result,
        integrity_report=integrity_report,
        confidence_results=confidence_results,
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
