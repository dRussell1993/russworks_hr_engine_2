from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from russworks.backtesting import BacktestResult
from russworks.calibration import CalibrationMetric, CalibrationResult
from russworks.config.weights import ScoringWeights
from russworks.dashboard import CalibrationDashboard, ModulePerformance

from .models import ModuleRecommendation, RecommendationReport, WeightRecommendation


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
    appearances: int
    hits: int
    hit_rate: float
    false_positives: int
    false_negatives: int
    confidence_score: float
    source: str


class WeightRecommendationEngine:
    def __init__(
        self,
        *,
        minimum_sample_size: int = 10,
        minimum_confidence: float = 0.25,
        maximum_adjustment_pct: float = 0.10,
    ) -> None:
        self.minimum_sample_size = minimum_sample_size
        self.minimum_confidence = minimum_confidence
        self.maximum_adjustment_pct = maximum_adjustment_pct

    def build_recommendations(
        self,
        *,
        calibration_result: CalibrationResult | None = None,
        dashboard: CalibrationDashboard | None = None,
        backtest_result: BacktestResult | None = None,
        current_weights: ScoringWeights | Mapping[str, float] | None = None,
    ) -> RecommendationReport:
        weights = _current_weight_map(current_weights)
        signals = _combined_signals(calibration_result, dashboard, backtest_result)
        recommendations = [
            self._module_recommendation(module, weights[module], signals.get(module))
            for module in _MODULE_ORDER
        ]
        rejected = [
            recommendation
            for recommendation in recommendations
            if recommendation.trend_direction in {"insufficient_sample", "noisy"}
        ]
        errors: list[str] = []
        if not signals:
            errors.append("Weight recommendations require calibration, dashboard, or backtest metrics.")
        return RecommendationReport(
            generated_at=_now(),
            modules=recommendations,
            rejected_modules=rejected,
            errors=errors,
        )

    def export_json(self, report: RecommendationReport, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / "recommendations.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.to_json(), encoding="utf-8")
        return output_path

    def _module_recommendation(
        self,
        module: str,
        current_weight: float,
        signal: _Signal | None,
    ) -> ModuleRecommendation:
        if signal is None:
            trend = "insufficient_sample"
            confidence = "low"
            suggested = current_weight
            metrics = {"appearances": 0, "source": "none"}
            reasoning = f"{module} has no available sample; hold the current weight until calibration data exists."
        else:
            metrics = _supporting_metrics(signal)
            trend, confidence, suggested, reasoning = self._evaluate_signal(module, current_weight, signal)

        suggested = round(suggested, 4)
        delta = round(suggested - current_weight, 4)
        weight_recommendation = WeightRecommendation(
            current_weight=current_weight,
            suggested_weight=suggested,
            delta=delta,
            confidence=confidence,
            trend_direction=trend,
            applied=False,
        )
        return ModuleRecommendation(
            module=module,
            current_weight=current_weight,
            suggested_weight=suggested,
            confidence=confidence,
            trend_direction=trend,
            supporting_metrics=metrics,
            reasoning=reasoning,
            recommendation=weight_recommendation,
        )

    def _evaluate_signal(
        self,
        module: str,
        current_weight: float,
        signal: _Signal,
    ) -> tuple[str, str, float, str]:
        if signal.appearances < self.minimum_sample_size:
            return (
                "insufficient_sample",
                "low",
                current_weight,
                f"{module} has {signal.appearances} appearances; at least {self.minimum_sample_size} are required before changing weights.",
            )

        if signal.confidence_score < self.minimum_confidence:
            return (
                "noisy",
                "low",
                current_weight,
                f"{module} confidence is {signal.confidence_score:.2f}, below the {self.minimum_confidence:.2f} noise threshold; hold weight.",
            )

        false_positive_pressure = _rate(signal.false_positives, signal.appearances)
        if signal.hit_rate >= 0.30 and signal.confidence_score >= 0.45 and false_positive_pressure <= 0.55:
            suggested = self._adjust_weight(current_weight, 1.0)
            return (
                "increase",
                _confidence_label(signal.confidence_score, signal.appearances),
                suggested,
                f"{module} is producing a {signal.hit_rate:.1%} hit rate with manageable false-positive pressure; recommend a measured increase.",
            )

        if false_positive_pressure >= 0.75 or (signal.false_positives > max(signal.hits * 2, 5) and signal.hit_rate < 0.20):
            suggested = self._adjust_weight(current_weight, -1.0)
            return (
                "decrease",
                _confidence_label(signal.confidence_score, signal.appearances),
                suggested,
                f"{module} is carrying high false-positive pressure relative to hits; recommend a measured reduction.",
            )

        return (
            "hold",
            _confidence_label(signal.confidence_score, signal.appearances),
            current_weight,
            f"{module} signal is usable but not decisive; keep the weight stable and continue tracking.",
        )

    def _adjust_weight(self, current_weight: float, direction: float) -> float:
        step = max(abs(current_weight) * self.maximum_adjustment_pct, 0.05)
        return current_weight + step * direction


def build_weight_recommendations(
    *,
    calibration_result: CalibrationResult | None = None,
    dashboard: CalibrationDashboard | None = None,
    backtest_result: BacktestResult | None = None,
    current_weights: ScoringWeights | Mapping[str, float] | None = None,
) -> RecommendationReport:
    return WeightRecommendationEngine().build_recommendations(
        calibration_result=calibration_result,
        dashboard=dashboard,
        backtest_result=backtest_result,
        current_weights=current_weights,
    )


def _combined_signals(
    calibration_result: CalibrationResult | None,
    dashboard: CalibrationDashboard | None,
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
        for trend in (dashboard.thirty_day_trends, dashboard.season_trends):
            if trend is None:
                continue
            for performance in trend.module_trends:
                signal = _from_dashboard_performance(performance, source=trend.label)
                signals[signal.module] = _prefer_signal(signals.get(signal.module), signal)

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


def _from_dashboard_performance(performance: ModulePerformance, *, source: str = "dashboard") -> _Signal:
    return _Signal(
        module=_display_name(performance.module),
        appearances=performance.appearances,
        hits=performance.wins,
        hit_rate=performance.hit_rate,
        false_positives=performance.false_positives,
        false_negatives=performance.false_negatives,
        confidence_score=performance.confidence_accuracy,
        source=source,
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


def _prefer_signal(existing: _Signal | None, incoming: _Signal) -> _Signal:
    if existing is None:
        return incoming
    if incoming.appearances > existing.appearances:
        return incoming
    if incoming.appearances == existing.appearances and incoming.confidence_score > existing.confidence_score:
        return incoming
    return existing


def _current_weight_map(current_weights: ScoringWeights | Mapping[str, float] | None) -> dict[str, float]:
    if isinstance(current_weights, Mapping):
        return {
            module: round(float(current_weights.get(module, _DEFAULT_ARCHETYPE_WEIGHT)), 4)
            for module in _MODULE_ORDER
        }

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


def _supporting_metrics(signal: _Signal) -> dict[str, int | float | str]:
    return {
        "appearances": signal.appearances,
        "hits": signal.hits,
        "hit_rate": signal.hit_rate,
        "false_positives": signal.false_positives,
        "false_negatives": signal.false_negatives,
        "confidence_score": signal.confidence_score,
        "source": signal.source,
    }


def _display_name(module: str) -> str:
    return _DISPLAY_NAMES.get(module, module)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


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


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
