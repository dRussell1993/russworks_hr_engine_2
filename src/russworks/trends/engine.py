from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from russworks.backtesting import BacktestResult, DailyBacktestSummary
from russworks.calibration import CalibrationResult
from russworks.dashboard import CalibrationDashboard, ModulePerformance
from russworks.recommendations import RecommendationReport

from .models import TrendMetric, TrendSummary


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

_DISPLAY_NAMES = {
    "Pitch Mix": "Pitch Mix Matchup",
    "Park Factor": "Park Factor V2",
}


@dataclass(frozen=True)
class _Point:
    module: str
    date: str
    appearances: int
    hits: int

    @property
    def hit_rate(self) -> float:
        return _rate(self.hits, self.appearances)


class TrendEngine:
    def build_trends(
        self,
        *,
        dashboard: CalibrationDashboard | None = None,
        calibration_result: CalibrationResult | None = None,
        recommendation_report: RecommendationReport | None = None,
        backtest_result: BacktestResult | None = None,
        daily_summaries: Iterable[DailyBacktestSummary] = (),
    ) -> TrendSummary:
        daily_points = _daily_points(backtest_result, daily_summaries)
        snapshot_points = _snapshot_points(dashboard, calibration_result, recommendation_report)
        metrics = [
            self._metric(module, daily_points.get(module, []), snapshot_points.get(module))
            for module in _MODULE_ORDER
        ]
        heating_up = [metric.module for metric in metrics if metric.classification == "Heating Up"]
        stable = [metric.module for metric in metrics if metric.classification == "Stable"]
        cooling_off = [metric.module for metric in metrics if metric.classification == "Cooling Off"]
        errors = []
        if not daily_points and not snapshot_points:
            errors.append("Trend engine requires dashboard, calibration, recommendation, or backtest metrics.")
        return TrendSummary(
            generated_at=_now(),
            metrics=metrics,
            heating_up=heating_up,
            stable=stable,
            cooling_off=cooling_off,
            summaries=_summaries(metrics, heating_up, stable, cooling_off),
            errors=errors,
        )

    def export_json(self, summary: TrendSummary, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / "trends.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(summary.to_json(), encoding="utf-8")
        return output_path

    def build_optimizer(self, summary: TrendSummary, *, calibration_result=None, dashboard=None, recommendation_report=None, backtest_result=None, current_weights=None):
        from russworks.optimizer import FormulaOptimizer

        return FormulaOptimizer().optimize(
            trend_summary=summary,
            calibration_result=calibration_result,
            dashboard=dashboard,
            recommendation_report=recommendation_report,
            backtest_result=backtest_result,
            current_weights=current_weights,
        )

    def _metric(self, module: str, points: list[_Point], snapshot: _Point | None) -> TrendMetric:
        sorted_points = sorted(points, key=lambda point: point.date)
        if sorted_points:
            season = _window_rate(sorted_points, None)
            seven = _window_rate(sorted_points, 7)
            fourteen = _window_rate(sorted_points, 14)
            thirty = _window_rate(sorted_points, 30)
            sample = sum(point.appearances for point in sorted_points)
            source = "backtest"
        elif snapshot is not None:
            season = snapshot.hit_rate
            seven = fourteen = thirty = season
            sample = snapshot.appearances
            source = snapshot.date
        else:
            season = seven = fourteen = thirty = 0.0
            sample = 0
            source = "none"

        classification = _classification(seven, season, sample)
        return TrendMetric(
            module=module,
            seven_day_trend=seven,
            fourteen_day_trend=fourteen,
            thirty_day_trend=thirty,
            season_trend=season,
            classification=classification,
            sample_size=sample,
            supporting_metrics={
                "source": source,
                "sample_size": sample,
                "seven_vs_season_delta": round(seven - season, 4),
                "thirty_vs_season_delta": round(thirty - season, 4),
            },
        )


def build_trends(
    *,
    dashboard: CalibrationDashboard | None = None,
    calibration_result: CalibrationResult | None = None,
    recommendation_report: RecommendationReport | None = None,
    backtest_result: BacktestResult | None = None,
    daily_summaries: Iterable[DailyBacktestSummary] = (),
) -> TrendSummary:
    return TrendEngine().build_trends(
        dashboard=dashboard,
        calibration_result=calibration_result,
        recommendation_report=recommendation_report,
        backtest_result=backtest_result,
        daily_summaries=daily_summaries,
    )


def _daily_points(
    backtest_result: BacktestResult | None,
    daily_summaries: Iterable[DailyBacktestSummary],
) -> dict[str, list[_Point]]:
    points: dict[str, list[_Point]] = defaultdict(list)
    summaries = list(daily_summaries)
    if backtest_result:
        summaries.extend(backtest_result.daily_summaries)
    for summary in summaries:
        appearances = max(summary.total_batters_reviewed, 0)
        values = {
            "YPI": summary.ypi_hits,
            "Veteran Bounce": summary.veteran_hits,
            "Catcher Power": summary.catcher_hits,
            "Weak Spot Collision": summary.weak_spot_hits,
            "Pitch Mix Matchup": summary.pitch_mix_hits,
        }
        for module, hits in values.items():
            points[module].append(_Point(module=module, date=summary.date, appearances=appearances, hits=hits))
    return dict(points)


def _snapshot_points(
    dashboard: CalibrationDashboard | None,
    calibration_result: CalibrationResult | None,
    recommendation_report: RecommendationReport | None,
) -> dict[str, _Point]:
    points: dict[str, _Point] = {}
    if calibration_result:
        for metric in calibration_result.metrics:
            module = _display_name(metric.module)
            points[module] = _Point(module=module, date="calibration", appearances=metric.appearances, hits=metric.hits)
    if dashboard:
        for performance in dashboard.modules:
            point = _from_performance(performance, "dashboard")
            points.setdefault(point.module, point)
        for trend in (dashboard.thirty_day_trends, dashboard.season_trends):
            if trend is None:
                continue
            for performance in trend.module_trends:
                point = _from_performance(performance, trend.label)
                existing = points.get(point.module)
                if existing is None or point.appearances > existing.appearances:
                    points[point.module] = point
    if recommendation_report:
        for recommendation in recommendation_report.modules:
            metrics = recommendation.supporting_metrics
            appearances = int(float(metrics.get("appearances", 0) or 0))
            hit_rate = float(metrics.get("hit_rate", 0.0) or 0.0)
            hits = int(round(appearances * hit_rate))
            points.setdefault(
                _display_name(recommendation.module),
                _Point(
                    module=_display_name(recommendation.module),
                    date="recommendations",
                    appearances=appearances,
                    hits=hits,
                ),
            )
    return points


def _from_performance(performance: ModulePerformance, source: str) -> _Point:
    return _Point(
        module=_display_name(performance.module),
        date=source,
        appearances=performance.appearances,
        hits=performance.wins,
    )


def _window_rate(points: list[_Point], limit: int | None) -> float:
    window = points if limit is None else points[-limit:]
    appearances = sum(point.appearances for point in window)
    hits = sum(point.hits for point in window)
    return _rate(hits, appearances)


def _classification(seven_day: float, season: float, sample_size: int) -> str:
    if sample_size <= 0:
        return "Stable"
    delta = seven_day - season
    if delta >= 0.05:
        return "Heating Up"
    if delta <= -0.05:
        return "Cooling Off"
    return "Stable"


def _summaries(
    metrics: list[TrendMetric],
    heating_up: list[str],
    stable: list[str],
    cooling_off: list[str],
) -> list[str]:
    if not metrics:
        return ["No trend metrics were available."]
    return [
        f"Heating Up modules: {', '.join(heating_up) if heating_up else 'none'}.",
        f"Stable modules: {', '.join(stable) if stable else 'none'}.",
        f"Cooling Off modules: {', '.join(cooling_off) if cooling_off else 'none'}.",
    ]


def _display_name(module: str) -> str:
    return _DISPLAY_NAMES.get(module, module)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
