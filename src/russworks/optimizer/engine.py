from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from russworks.backtesting import BacktestResult
from russworks.calibration import CalibrationMetric, CalibrationResult
from russworks.config.weights import ScoringWeights
from russworks.dashboard import CalibrationDashboard, ModulePerformance
from russworks.recommendations import RecommendationReport
from russworks.trends import TrendSummary

from .models import OptimizationResult, OptimizationScenario


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

_DEFAULT_ARCHETYPE_WEIGHT = 1.0


@dataclass(frozen=True)
class _Signal:
    module: str
    appearances: int = 0
    hits: int = 0
    hit_rate: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0
    confidence_score: float = 0.0
    trend_classification: str = "Stable"
    recommendation_direction: str = "hold"
    trend_delta: float = 0.0
    source: str = "none"


class FormulaOptimizer:
    def __init__(
        self,
        *,
        minimum_sample_size: int = 10,
        minimum_confidence: float = 0.25,
        simulation_step_pct: float = 0.10,
    ) -> None:
        self.minimum_sample_size = minimum_sample_size
        self.minimum_confidence = minimum_confidence
        self.simulation_step_pct = simulation_step_pct

    def optimize(
        self,
        *,
        calibration_result: CalibrationResult | None = None,
        dashboard: CalibrationDashboard | None = None,
        recommendation_report: RecommendationReport | None = None,
        trend_summary: TrendSummary | None = None,
        backtest_result: BacktestResult | None = None,
        current_weights: ScoringWeights | Mapping[str, float] | None = None,
    ) -> OptimizationResult:
        weights = _current_weight_map(current_weights)
        signals = _combined_signals(
            calibration_result=calibration_result,
            dashboard=dashboard,
            recommendation_report=recommendation_report,
            trend_summary=trend_summary,
            backtest_result=backtest_result,
        )
        scenarios = [self._scenario(module, weights[module], signals.get(module)) for module in _MODULE_ORDER]
        rejected = [scenario for scenario in scenarios if scenario.rejected]
        errors: list[str] = []
        if not signals:
            errors.append("Formula optimization requires calibration, dashboard, recommendation, trend, or backtest metrics.")
        return OptimizationResult(
            generated_at=_now(),
            scenarios=scenarios,
            rejected_scenarios=rejected,
            summaries=_summaries(scenarios),
            errors=errors,
        )

    def export_json(self, result: OptimizationResult, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / "optimizer_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.to_json(), encoding="utf-8")
        return output_path

    def _scenario(self, module: str, current_weight: float, signal: _Signal | None) -> OptimizationScenario:
        if signal is None:
            signal = _Signal(module=module)

        rejected, reject_reason = self._rejection(signal)
        if rejected:
            direction = "hold"
            simulated_weight = current_weight
            expected_impact = 0.0
            reasoning = reject_reason
            confidence = "low"
        else:
            direction = _recommended_direction(signal)
            simulated_weight = _simulate_weight(current_weight, direction, self.simulation_step_pct)
            expected_impact = _expected_impact(signal, direction)
            confidence = _confidence_label(signal.confidence_score, signal.appearances)
            reasoning = _reasoning(module, signal, direction, expected_impact)

        change_pct = _rate(simulated_weight - current_weight, abs(current_weight) or 1.0)
        return OptimizationScenario(
            module=module,
            current_weight=round(current_weight, 4),
            simulated_weight=round(simulated_weight, 4),
            simulated_change_pct=round(change_pct, 4),
            historical_performance=round(signal.hit_rate, 4),
            expected_impact=round(expected_impact, 4),
            confidence_level=confidence,
            recommendation=direction,
            rejected=rejected,
            reasoning=reasoning,
            supporting_metrics=_supporting_metrics(signal),
        )

    def _rejection(self, signal: _Signal) -> tuple[bool, str]:
        if signal.appearances < self.minimum_sample_size:
            return (
                True,
                f"{signal.module} has {signal.appearances} appearances; at least {self.minimum_sample_size} are required before optimization.",
            )
        if signal.confidence_score < self.minimum_confidence:
            return (
                True,
                f"{signal.module} confidence is {signal.confidence_score:.2f}, below the {self.minimum_confidence:.2f} noise threshold; no simulated change recommended.",
            )
        return False, ""


def optimize_formula(
    *,
    calibration_result: CalibrationResult | None = None,
    dashboard: CalibrationDashboard | None = None,
    recommendation_report: RecommendationReport | None = None,
    trend_summary: TrendSummary | None = None,
    backtest_result: BacktestResult | None = None,
    current_weights: ScoringWeights | Mapping[str, float] | None = None,
) -> OptimizationResult:
    return FormulaOptimizer().optimize(
        calibration_result=calibration_result,
        dashboard=dashboard,
        recommendation_report=recommendation_report,
        trend_summary=trend_summary,
        backtest_result=backtest_result,
        current_weights=current_weights,
    )


def _combined_signals(
    *,
    calibration_result: CalibrationResult | None,
    dashboard: CalibrationDashboard | None,
    recommendation_report: RecommendationReport | None,
    trend_summary: TrendSummary | None,
    backtest_result: BacktestResult | None,
) -> dict[str, _Signal]:
    signals: dict[str, _Signal] = {}
    if calibration_result:
        for metric in calibration_result.metrics:
            signal = _from_calibration_metric(metric)
            signals[signal.module] = signal
    if backtest_result and backtest_result.summary:
        for signal in _from_backtest(backtest_result):
            signals.setdefault(signal.module, signal)
    if dashboard:
        for performance in dashboard.modules:
            signal = _from_dashboard_performance(performance)
            signals[signal.module] = _prefer_signal(signals.get(signal.module), signal)
    if recommendation_report:
        for recommendation in recommendation_report.modules:
            module = _display_name(recommendation.module)
            base = signals.get(module, _Signal(module=module))
            metrics = recommendation.supporting_metrics
            appearances = int(float(metrics.get("appearances", base.appearances) or 0))
            hit_rate = float(metrics.get("hit_rate", base.hit_rate) or 0.0)
            confidence = _confidence_from_label(recommendation.confidence, base.confidence_score)
            signals[module] = _merge_signal(
                base,
                _Signal(
                    module=module,
                    appearances=max(base.appearances, appearances),
                    hits=base.hits or int(round(appearances * hit_rate)),
                    hit_rate=base.hit_rate or hit_rate,
                    false_positives=base.false_positives,
                    false_negatives=base.false_negatives,
                    confidence_score=max(base.confidence_score, confidence),
                    recommendation_direction=recommendation.trend_direction,
                    source="recommendations",
                ),
            )
    if trend_summary:
        for metric in trend_summary.metrics:
            module = _display_name(metric.module)
            base = signals.get(module, _Signal(module=module))
            signals[module] = _merge_signal(
                base,
                _Signal(
                    module=module,
                    appearances=max(base.appearances, metric.sample_size),
                    hits=base.hits or int(round(metric.season_trend * metric.sample_size)),
                    hit_rate=base.hit_rate or metric.season_trend,
                    false_positives=base.false_positives,
                    false_negatives=base.false_negatives,
                    confidence_score=max(base.confidence_score, _trend_confidence(metric.sample_size)),
                    trend_classification=metric.classification,
                    trend_delta=float(metric.supporting_metrics.get("seven_vs_season_delta", metric.seven_day_trend - metric.season_trend)),
                    source="trends",
                ),
            )
    return {module: signals[module] for module in _MODULE_ORDER if module in signals}


def _from_calibration_metric(metric: CalibrationMetric) -> _Signal:
    return _Signal(
        module=_display_name(metric.module),
        appearances=metric.appearances,
        hits=metric.hits,
        hit_rate=metric.hit_rate,
        false_positives=metric.false_positives,
        false_negatives=metric.false_negatives,
        confidence_score=metric.confidence_score,
        source="calibration",
    )


def _from_dashboard_performance(performance: ModulePerformance) -> _Signal:
    return _Signal(
        module=_display_name(performance.module),
        appearances=performance.appearances,
        hits=performance.wins,
        hit_rate=performance.hit_rate,
        false_positives=performance.false_positives,
        false_negatives=performance.false_negatives,
        confidence_score=performance.confidence_accuracy,
        source="dashboard",
    )


def _from_backtest(backtest_result: BacktestResult) -> list[_Signal]:
    summary = backtest_result.summary
    assert summary is not None
    appearances = summary.total_batters_reviewed
    total_hrs = summary.total_hrs_hit
    values = [
        ("YPI", summary.ypi_hits),
        ("Veteran Bounce", summary.veteran_hits),
        ("Catcher Power", summary.catcher_hits),
        ("Weak Spot Collision", summary.weak_spot_hits),
        ("Pitch Mix Matchup", summary.pitch_mix_hits),
    ]
    return [
        _Signal(
            module=module,
            appearances=appearances,
            hits=hits,
            hit_rate=_rate(hits, appearances),
            false_positives=max(0, appearances - hits),
            false_negatives=max(0, total_hrs - hits),
            confidence_score=_confidence(appearances, hits, max(0, appearances - hits), max(0, total_hrs - hits)),
            source="backtest",
        )
        for module, hits in values
    ]


def _merge_signal(base: _Signal, incoming: _Signal) -> _Signal:
    return _Signal(
        module=base.module,
        appearances=max(base.appearances, incoming.appearances),
        hits=base.hits or incoming.hits,
        hit_rate=base.hit_rate or incoming.hit_rate,
        false_positives=base.false_positives or incoming.false_positives,
        false_negatives=base.false_negatives or incoming.false_negatives,
        confidence_score=max(base.confidence_score, incoming.confidence_score),
        trend_classification=incoming.trend_classification if incoming.trend_classification != "Stable" else base.trend_classification,
        recommendation_direction=incoming.recommendation_direction if incoming.recommendation_direction != "hold" else base.recommendation_direction,
        trend_delta=incoming.trend_delta or base.trend_delta,
        source=incoming.source if base.source == "none" else f"{base.source}+{incoming.source}",
    )


def _prefer_signal(existing: _Signal | None, incoming: _Signal) -> _Signal:
    if existing is None:
        return incoming
    if incoming.appearances > existing.appearances:
        return incoming
    if incoming.appearances == existing.appearances and incoming.confidence_score > existing.confidence_score:
        return incoming
    return existing


def _recommended_direction(signal: _Signal) -> str:
    false_positive_pressure = _rate(signal.false_positives, signal.appearances)
    if signal.recommendation_direction == "increase" or signal.trend_classification == "Heating Up":
        if signal.hit_rate >= 0.20 and false_positive_pressure <= 0.70:
            return "increase"
    if signal.recommendation_direction == "decrease" or signal.trend_classification == "Cooling Off":
        return "decrease"
    if signal.hit_rate >= 0.30 and signal.confidence_score >= 0.45 and false_positive_pressure <= 0.55:
        return "increase"
    if false_positive_pressure >= 0.75 or (signal.false_positives > max(signal.hits * 2, 5) and signal.hit_rate < 0.20):
        return "decrease"
    return "hold"


def _simulate_weight(current_weight: float, direction: str, step_pct: float) -> float:
    if direction == "hold":
        return current_weight
    step = max(abs(current_weight) * step_pct, 0.05)
    if direction == "increase":
        return current_weight + step
    return current_weight - step


def _expected_impact(signal: _Signal, direction: str) -> float:
    if direction == "hold":
        return 0.0
    base = signal.hit_rate * signal.confidence_score
    trend_bonus = abs(signal.trend_delta) * 0.5
    penalty = _rate(signal.false_positives, signal.appearances) * 0.15
    impact = max(0.01, abs(base + trend_bonus - penalty))
    return impact if direction == "increase" else -impact


def _reasoning(module: str, signal: _Signal, direction: str, expected_impact: float) -> str:
    if direction == "increase":
        return f"{module} has usable history, {signal.trend_classification} trend pressure, and expected positive impact of {expected_impact:.2f}; recommend simulated increase only."
    if direction == "decrease":
        return f"{module} shows cooling or false-positive pressure with expected impact of {expected_impact:.2f}; recommend simulated reduction only."
    return f"{module} signal is mixed or stable; hold current weight while collecting more evidence."


def _supporting_metrics(signal: _Signal) -> dict[str, int | float | str]:
    return {
        "appearances": signal.appearances,
        "hits": signal.hits,
        "hit_rate": signal.hit_rate,
        "false_positives": signal.false_positives,
        "false_negatives": signal.false_negatives,
        "confidence_score": signal.confidence_score,
        "trend_classification": signal.trend_classification,
        "recommendation_direction": signal.recommendation_direction,
        "trend_delta": signal.trend_delta,
        "source": signal.source,
    }


def _current_weight_map(current_weights: ScoringWeights | Mapping[str, float] | None) -> dict[str, float]:
    if isinstance(current_weights, Mapping):
        return {module: round(float(current_weights.get(module, _DEFAULT_ARCHETYPE_WEIGHT)), 4) for module in _MODULE_ORDER}
    weights = current_weights or ScoringWeights.defaults()
    return {
        "TAG": _representative_weight(weights.tag, "base"),
        "CPS": _representative_weight(weights.cps, "base"),
        "LSTM": _representative_weight(weights.lstm, "slot_4"),
        "Environment": _section_average(weights.environment),
        "Umpire": _section_average(weights.umpire),
        "PVS": _section_average(weights.pvs),
        "Weak Spot Collision": _DEFAULT_ARCHETYPE_WEIGHT,
        "YPI": _DEFAULT_ARCHETYPE_WEIGHT,
        "Veteran Bounce": _DEFAULT_ARCHETYPE_WEIGHT,
        "Catcher Power": _DEFAULT_ARCHETYPE_WEIGHT,
        "Pitch Mix Matchup": _DEFAULT_ARCHETYPE_WEIGHT,
        "Bullpen Exposure": _DEFAULT_ARCHETYPE_WEIGHT,
        "Park Factor V2": _DEFAULT_ARCHETYPE_WEIGHT,
    }


def _representative_weight(section: Mapping[str, float], key: str) -> float:
    return round(float(section.get(key, _section_average(section))), 4)


def _section_average(section: Mapping[str, float]) -> float:
    values = [abs(float(value)) for value in section.values()]
    if not values:
        return _DEFAULT_ARCHETYPE_WEIGHT
    return round(sum(values) / len(values), 4)


def _confidence_from_label(label: str, fallback: float) -> float:
    lowered = label.lower()
    if lowered == "high":
        return max(fallback, 0.75)
    if lowered == "medium":
        return max(fallback, 0.50)
    if lowered == "low":
        return max(fallback, 0.25)
    return fallback


def _trend_confidence(sample_size: int) -> float:
    if sample_size >= 50:
        return 0.70
    if sample_size >= 20:
        return 0.50
    if sample_size >= 10:
        return 0.35
    return 0.10


def _confidence(appearances: int, hits: int, false_positives: int, false_negatives: int) -> float:
    if appearances <= 0:
        return 0.0
    precision = _rate(hits, appearances)
    penalty = min(0.35, (false_positives + false_negatives) / max(appearances + false_negatives, 1) * 0.35)
    sample = min(1.0, appearances / 20.0)
    return round(max(0.0, min(1.0, sample * 0.45 + precision * 0.55 - penalty)), 4)


def _confidence_label(confidence_score: float, appearances: int) -> str:
    if appearances >= 50 and confidence_score >= 0.65:
        return "high"
    if appearances >= 20 and confidence_score >= 0.40:
        return "medium"
    return "low"


def _summaries(scenarios: list[OptimizationScenario]) -> list[str]:
    increases = [scenario.module for scenario in scenarios if scenario.recommendation == "increase" and not scenario.rejected]
    decreases = [scenario.module for scenario in scenarios if scenario.recommendation == "decrease" and not scenario.rejected]
    rejected = [scenario.module for scenario in scenarios if scenario.rejected]
    return [
        f"Simulated increases: {', '.join(increases) if increases else 'none'}.",
        f"Simulated reductions: {', '.join(decreases) if decreases else 'none'}.",
        f"Rejected for sample/noise: {', '.join(rejected) if rejected else 'none'}.",
        "Live weights were not modified.",
    ]


def _display_name(module: str) -> str:
    return _DISPLAY_NAMES.get(module, module)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
