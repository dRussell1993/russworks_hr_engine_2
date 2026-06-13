from __future__ import annotations

from collections import Counter
from typing import Callable, Iterable, Sequence

from russworks.backtesting import BacktestResult
from russworks.postmortem import ActualHomeRunEntry, PostMortemReport
from russworks.review import BatterReview, BatterReviewResult

from .models import CalibrationMetric, CalibrationRecommendation, CalibrationResult


ModuleDetector = Callable[[BatterReview], bool]


_MODULE_DETECTORS: dict[str, ModuleDetector] = {
    "TAG": lambda review: review.tag_contribution >= 75.0,
    "CPS": lambda review: review.cps_contribution >= 75.0,
    "LSTM": lambda review: review.lstm_score > 0.0,
    "PVS": lambda review: review.pvs_contribution > 0.0,
    "Environment": lambda review: review.environment_score > 0.0,
    "Umpire": lambda review: review.umpire_score > 0.0,
    "Weak Spot Collision": lambda review: review.weak_spot_collision_flag or review.weak_spot_collision_score >= 25.0,
    "YPI": lambda review: review.ypi_flag or review.ypi_grade in {"Elite", "Strong", "Emerging"},
    "Veteran Bounce": lambda review: review.veteran_bounce_flag or review.veteran_bounce_grade in {"Elite", "Strong", "Moderate"},
    "Catcher Power": lambda review: review.catcher_power_flag or review.catcher_power_grade in {"Elite", "Strong", "Moderate"},
    "Pitch Mix": lambda review: review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"},
    "Bullpen Exposure": lambda review: review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate"},
    "Park Factor": lambda review: review.park_factor_grade in {"Elite", "Strong", "Moderate"},
}


class FormulaCalibrationEngine:
    def calibrate_reviews(
        self,
        step3_results: BatterReviewResult | Sequence[BatterReviewResult] | Sequence[BatterReview],
        actual_home_runs: Iterable[ActualHomeRunEntry | dict[str, object]],
        *,
        postmortem_reports: Sequence[PostMortemReport] = (),
    ) -> CalibrationResult:
        reviews = _flatten_reviews(step3_results)
        actual_keys = [_actual_key(entry) for entry in actual_home_runs]
        actual_key_set = set(actual_keys)
        review_index = {_review_key(review): review for review in reviews}

        metrics = [
            _metric_for_module(module, detector, reviews, actual_key_set, review_index)
            for module, detector in _MODULE_DETECTORS.items()
        ]
        strengths = sorted(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, metric.hits), reverse=True)
        weaknesses = sorted(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, -metric.false_positives))
        recommendations = _recommend_adjustments(metrics, postmortem_reports)
        trends = _trend_summaries(metrics, postmortem_reports)
        errors = [] if reviews else ["Formula calibration requires Step 3 batter reviews."]
        return CalibrationResult(
            metrics=metrics,
            strength_rankings=strengths,
            weakness_rankings=weaknesses,
            recommended_adjustments=recommendations,
            trend_summaries=trends,
            errors=errors,
        )

    def calibrate_backtest(self, backtest_result: BacktestResult) -> CalibrationResult:
        if backtest_result.summary is None:
            return CalibrationResult(errors=["Formula calibration requires a BacktestResult summary."])

        summary = backtest_result.summary
        metrics = [
            _summary_metric("YPI", summary.total_batters_reviewed, summary.ypi_hits, summary.total_hrs_hit),
            _summary_metric("Veteran Bounce", summary.total_batters_reviewed, summary.veteran_hits, summary.total_hrs_hit),
            _summary_metric("Catcher Power", summary.total_batters_reviewed, summary.catcher_hits, summary.total_hrs_hit),
            _summary_metric("Weak Spot Collision", summary.total_batters_reviewed, summary.weak_spot_hits, summary.total_hrs_hit),
            _summary_metric("Pitch Mix", summary.total_batters_reviewed, summary.pitch_mix_hits, summary.total_hrs_hit),
        ]
        strengths = sorted(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, metric.hits), reverse=True)
        weaknesses = sorted(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, -metric.false_positives))
        recommendations = _recommend_adjustments(metrics, ())
        trends = [
            f"{summary.start_date} to {summary.end_date}: Step 3 hit rate {summary.step3_hit_rate:.1%}.",
            f"{summary.start_date} to {summary.end_date}: Step 5 hit rate {summary.step5_hit_rate:.1%}.",
            *_trend_summaries(metrics, ()),
        ]
        return CalibrationResult(
            metrics=metrics,
            strength_rankings=strengths,
            weakness_rankings=weaknesses,
            recommended_adjustments=recommendations,
            trend_summaries=trends,
            errors=list(backtest_result.errors),
        )

    def export_json(self, result: CalibrationResult, *, indent: int | None = 2) -> str:
        return result.to_json(indent=indent)

    def build_dashboard(self, result: CalibrationResult, *, postmortem_reports: Sequence[PostMortemReport] = (), backtest_result: BacktestResult | None = None):
        from russworks.dashboard import CalibrationDashboardEngine

        return CalibrationDashboardEngine().build_dashboard(
            calibration_result=result,
            postmortem_reports=postmortem_reports,
            backtest_result=backtest_result,
        )

    def build_weight_recommendations(
        self,
        result: CalibrationResult,
        *,
        dashboard=None,
        backtest_result: BacktestResult | None = None,
        current_weights=None,
    ):
        from russworks.recommendations import WeightRecommendationEngine

        return WeightRecommendationEngine().build_recommendations(
            calibration_result=result,
            dashboard=dashboard,
            backtest_result=backtest_result,
            current_weights=current_weights,
        )


def calibrate_formula(
    step3_results: BatterReviewResult | Sequence[BatterReviewResult] | Sequence[BatterReview],
    actual_home_runs: Iterable[ActualHomeRunEntry | dict[str, object]],
) -> CalibrationResult:
    return FormulaCalibrationEngine().calibrate_reviews(step3_results, actual_home_runs)


def _metric_for_module(
    module: str,
    detector: ModuleDetector,
    reviews: Sequence[BatterReview],
    actual_key_set: set[tuple[str, str]],
    review_index: dict[tuple[str, str], BatterReview],
) -> CalibrationMetric:
    appearances = [review for review in reviews if detector(review)]
    appearance_keys = {_review_key(review) for review in appearances}
    hits = sum(1 for key in actual_key_set if key in appearance_keys)
    false_positives = max(0, len(appearance_keys - actual_key_set))
    false_negatives = sum(1 for key in actual_key_set if key in review_index and key not in appearance_keys)
    hit_rate = _rate(hits, len(appearances))
    confidence = _confidence_score(len(appearances), hits, false_positives, false_negatives)
    return CalibrationMetric(
        module=module,
        appearances=len(appearances),
        hits=hits,
        hit_rate=hit_rate,
        false_positives=false_positives,
        false_negatives=false_negatives,
        confidence_score=confidence,
    )


def _summary_metric(module: str, appearances: int, hits: int, total_hrs: int) -> CalibrationMetric:
    false_positives = max(0, appearances - hits)
    false_negatives = max(0, total_hrs - hits)
    hit_rate = _rate(hits, appearances)
    return CalibrationMetric(
        module=module,
        appearances=appearances,
        hits=hits,
        hit_rate=hit_rate,
        false_positives=false_positives,
        false_negatives=false_negatives,
        confidence_score=_confidence_score(appearances, hits, false_positives, false_negatives),
    )


def _recommend_adjustments(
    metrics: Sequence[CalibrationMetric],
    postmortem_reports: Sequence[PostMortemReport],
) -> list[CalibrationRecommendation]:
    postmortem_pressure = _postmortem_pressure(postmortem_reports)
    recommendations: list[CalibrationRecommendation] = []
    for metric in metrics:
        if metric.appearances == 0:
            recommendations.append(
                CalibrationRecommendation(
                    module=metric.module,
                    action="needs_more_data",
                    suggested_delta=0.0,
                    confidence="low",
                    rationale="No module appearances were available; do not adjust weights.",
                )
            )
            continue
        if metric.false_negatives > metric.hits and metric.hit_rate >= 0.20:
            action = "monitor_or_slightly_increase"
            delta = min(0.05, 0.01 * metric.false_negatives)
            rationale = "Module found some winners but missed more actual HRs than it captured."
        elif metric.false_positives > max(metric.hits * 2, 3):
            action = "review_or_slightly_reduce"
            delta = -min(0.05, 0.01 * (metric.false_positives - metric.hits))
            rationale = "Module generated a high false-positive load relative to hits."
        elif metric.hit_rate >= 0.30 and metric.hits >= 2:
            action = "strength_confirmed"
            delta = 0.0
            rationale = "Module produced a strong hit rate; keep weights stable until sample size grows."
        else:
            action = "hold_current_weight"
            delta = 0.0
            rationale = "Module signal is inconclusive; recommendations only."

        pressure_count = postmortem_pressure.get(metric.module, 0)
        if pressure_count and action == "hold_current_weight":
            action = "review_postmortem_pressure"
            delta = -min(0.03, pressure_count * 0.005)
            rationale = "Post-mortem false-positive pressure exists; audit before changing weights."

        recommendations.append(
            CalibrationRecommendation(
                module=metric.module,
                action=action,
                suggested_delta=round(delta, 3),
                confidence=_confidence_label(metric.appearances),
                rationale=rationale,
            )
        )
    return recommendations


def _trend_summaries(
    metrics: Sequence[CalibrationMetric],
    postmortem_reports: Sequence[PostMortemReport],
) -> list[str]:
    if not metrics:
        return ["No calibration metrics were available."]

    strongest = max(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, metric.hits))
    weakest = min(metrics, key=lambda metric: (metric.confidence_score, metric.hit_rate, -metric.false_positives))
    trends = [
        f"Strongest module: {strongest.module} with {strongest.hits}/{strongest.appearances} hits and {strongest.confidence_score:.2f} confidence.",
        f"Weakest module: {weakest.module} with {weakest.false_positives} false positives and {weakest.false_negatives} false negatives.",
    ]
    pressure = _postmortem_pressure(postmortem_reports)
    if pressure:
        module, count = pressure.most_common(1)[0]
        trends.append(f"Post-mortem pressure: {module} appeared in {count} false-positive or adjustment signals.")
    return trends


def _postmortem_pressure(postmortem_reports: Sequence[PostMortemReport]) -> Counter:
    pressure: Counter = Counter()
    for report in postmortem_reports:
        for entry in report.false_positive_log:
            pressure.update(entry.overweighted_modules)
        for entry in report.adjustment_log:
            if "reduce" in entry.direction or "false_positive" in entry.direction:
                pressure[entry.module] += entry.evidence_count
    return pressure


def _flatten_reviews(
    value: BatterReviewResult | Sequence[BatterReviewResult] | Sequence[BatterReview],
) -> list[BatterReview]:
    if isinstance(value, BatterReviewResult):
        return list(value.reviews)
    flattened: list[BatterReview] = []
    for item in value:
        if isinstance(item, BatterReviewResult):
            flattened.extend(item.reviews)
        elif isinstance(item, BatterReview):
            flattened.append(item)
    return flattened


def _actual_key(entry: ActualHomeRunEntry | dict[str, object]) -> tuple[str, str]:
    if isinstance(entry, ActualHomeRunEntry):
        return (entry.team.lower(), entry.batter.lower())
    return (str(entry["team"]).lower(), str(entry["batter"]).lower())


def _review_key(review: BatterReview) -> tuple[str, str]:
    return (review.team.lower(), review.batter_name.lower())


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _confidence_score(appearances: int, hits: int, false_positives: int, false_negatives: int) -> float:
    if appearances <= 0:
        return 0.0
    sample = min(1.0, appearances / 20.0)
    precision = _rate(hits, appearances)
    penalty = min(0.35, (false_positives + false_negatives) / max(appearances + false_negatives, 1) * 0.35)
    return round(max(0.0, min(1.0, sample * 0.45 + precision * 0.55 - penalty)), 4)


def _confidence_label(appearances: int) -> str:
    if appearances >= 50:
        return "high"
    if appearances >= 20:
        return "medium"
    return "low"
