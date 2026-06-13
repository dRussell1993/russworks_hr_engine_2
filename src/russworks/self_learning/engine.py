from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING, Sequence

from .models import (
    LearningInsight,
    LearningObservation,
    LearningRecommendation,
    LearningRecommendationType,
    LearningSummary,
    SelfLearningReport,
)


if TYPE_CHECKING:
    from russworks.backtesting import BacktestResult
    from russworks.calibration import CalibrationResult
    from russworks.dashboard import CalibrationDashboard
    from russworks.optimizer import OptimizationResult
    from russworks.recommendations import RecommendationReport
    from russworks.simulation import SimulationResult
    from russworks.trends import TrendSummary


class SelfLearningEngine:
    def build_report(
        self,
        *,
        calibration_result: CalibrationResult | None = None,
        backtest_result: BacktestResult | None = None,
        trend_summary: TrendSummary | None = None,
        optimizer_result: OptimizationResult | None = None,
        simulation_result: SimulationResult | None = None,
        recommendation_report: RecommendationReport | None = None,
        dashboard: CalibrationDashboard | None = None,
    ) -> SelfLearningReport:
        observations = [
            *_calibration_observations(calibration_result),
            *_backtest_observations(backtest_result),
            *_trend_observations(trend_summary),
            *_optimizer_observations(optimizer_result),
            *_simulation_observations(simulation_result),
            *_weight_recommendation_observations(recommendation_report),
            *_dashboard_observations(dashboard),
        ]
        insights = _insights(observations, dashboard=dashboard, trend_summary=trend_summary)
        recommendations = _recommendations(
            observations,
            insights,
            simulation_result=simulation_result,
            recommendation_report=recommendation_report,
            optimizer_result=optimizer_result,
        )
        summary = LearningSummary(
            top_performing_modules=_top_modules(observations, dashboard),
            underperforming_modules=_weak_modules(observations, dashboard),
            consistent_strengths=[insight.subject for insight in insights if insight.category == "consistent_strength"],
            consistent_weaknesses=[insight.subject for insight in insights if insight.category == "consistent_weakness"],
            emerging_trends=[insight.subject for insight in insights if insight.category == "emerging_trend"],
            confidence_ranked_recommendations=sorted(recommendations, key=lambda item: item.confidence, reverse=True),
        )
        return SelfLearningReport(
            generated_at=_now(),
            observations=observations,
            insights=insights,
            recommendations=recommendations,
            summary=summary,
            notes=[
                "Self-learning recommendations are advisory only.",
                "This engine never modifies weights, scores, or slips.",
            ],
        )

    def export_json(self, report: SelfLearningReport, output_dir: str | Path = "data/self_learning") -> Path:
        output_path = Path(output_dir) / "self_learning_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.to_json(), encoding="utf-8")
        return output_path


def build_self_learning_report(**kwargs) -> SelfLearningReport:
    return SelfLearningEngine().build_report(**kwargs)


def _calibration_observations(result: CalibrationResult | None) -> list[LearningObservation]:
    if result is None:
        return []
    observations = [
        LearningObservation(
            source="calibration",
            subject=metric.module,
            metric="hit_rate",
            value=metric.hit_rate,
            confidence=_confidence(metric.confidence_score, metric.appearances),
            summary=f"{metric.module} calibration hit rate {metric.hit_rate:.1%} over {metric.appearances} appearances.",
        )
        for metric in result.metrics
    ]
    for recommendation in result.recommended_adjustments:
        observations.append(
            LearningObservation(
                source="calibration",
                subject=recommendation.module,
                metric="recommended_adjustment",
                value=recommendation.suggested_delta,
                confidence=_confidence_label(recommendation.confidence),
                summary=recommendation.rationale,
            )
        )
    return observations


def _backtest_observations(result: BacktestResult | None) -> list[LearningObservation]:
    if result is None or result.summary is None:
        return []
    summary = result.summary
    return [
        LearningObservation("backtesting", "Step 3", "hit_rate", summary.step3_hit_rate, _confidence(summary.step3_hit_rate, summary.total_batters_reviewed), "Step 3 historical hit rate."),
        LearningObservation("backtesting", "Step 4", "hit_rate", summary.step4_hit_rate, _confidence(summary.step4_hit_rate, summary.total_batters_reviewed), "Step 4 historical hit rate."),
        LearningObservation("backtesting", "Step 5", "hit_rate", summary.step5_hit_rate, _confidence(summary.step5_hit_rate, summary.total_batters_reviewed), "Step 5 historical hit rate."),
        LearningObservation("backtesting", "YPI", "hit_rate", summary.ypi_hit_rate, _confidence(summary.ypi_hit_rate, summary.total_batters_reviewed), "YPI historical hit rate."),
        LearningObservation("backtesting", "Veteran Bounce", "hit_rate", summary.veteran_hit_rate, _confidence(summary.veteran_hit_rate, summary.total_batters_reviewed), "Veteran Bounce historical hit rate."),
        LearningObservation("backtesting", "Catcher Power", "hit_rate", summary.catcher_hit_rate, _confidence(summary.catcher_hit_rate, summary.total_batters_reviewed), "Catcher Power historical hit rate."),
        LearningObservation("backtesting", "Weak Spot Collision", "hit_rate", summary.weak_spot_hit_rate, _confidence(summary.weak_spot_hit_rate, summary.total_batters_reviewed), "Weak Spot Collision historical hit rate."),
        LearningObservation("backtesting", "Pitch Mix Matchup", "hit_rate", summary.pitch_mix_hit_rate, _confidence(summary.pitch_mix_hit_rate, summary.total_batters_reviewed), "Pitch Mix historical hit rate."),
    ]


def _trend_observations(result: TrendSummary | None) -> list[LearningObservation]:
    if result is None:
        return []
    return [
        LearningObservation(
            source="trends",
            subject=metric.module,
            metric="season_trend",
            value=metric.season_trend,
            confidence=_confidence(metric.season_trend, metric.sample_size),
            summary=f"{metric.module} trend is {metric.classification}.",
        )
        for metric in result.metrics
    ]


def _optimizer_observations(result: OptimizationResult | None) -> list[LearningObservation]:
    if result is None:
        return []
    return [
        LearningObservation(
            source="optimizer",
            subject=scenario.module,
            metric="expected_impact",
            value=scenario.expected_impact,
            confidence=0.0 if scenario.rejected else _confidence_label(scenario.confidence_level),
            summary=scenario.reasoning,
        )
        for scenario in result.scenarios
    ]


def _simulation_observations(result: SimulationResult | None) -> list[LearningObservation]:
    if result is None or result.summary is None:
        return []
    summary = result.summary
    return [
        LearningObservation("simulation", "Portfolio", "expected_hit_rate", summary.expected_hit_rate, _confidence(summary.expected_hit_rate, summary.simulation_count), "Monte Carlo expected portfolio hit rate."),
        LearningObservation("simulation", "Portfolio", "expected_roi", summary.expected_roi, _confidence(abs(summary.expected_roi), summary.simulation_count), "Monte Carlo expected ROI."),
        LearningObservation("simulation", "Portfolio", "drawdown_risk", summary.drawdown_risk, _confidence(summary.drawdown_risk, summary.simulation_count), "Monte Carlo drawdown risk."),
        LearningObservation("simulation", "Portfolio", "risk_grade", summary.risk_grade.value, 0.8, f"Simulation risk grade {summary.risk_grade.value}."),
    ]


def _weight_recommendation_observations(result: RecommendationReport | None) -> list[LearningObservation]:
    if result is None:
        return []
    return [
        LearningObservation(
            source="weight_recommendations",
            subject=item.module,
            metric="suggested_weight_delta",
            value=item.suggested_weight - item.current_weight,
            confidence=_confidence_label(item.confidence),
            summary=item.reasoning or f"{item.module} recommendation trend {item.trend_direction}.",
        )
        for item in result.modules
    ]


def _dashboard_observations(dashboard: CalibrationDashboard | None) -> list[LearningObservation]:
    if dashboard is None:
        return []
    observations = []
    for module in dashboard.top_performing_modules:
        observations.append(LearningObservation("dashboard", module.module, "top_performer", module.hit_rate, _confidence(module.confidence_accuracy, module.appearances), f"{module.module} is a dashboard top performer."))
    for module in dashboard.worst_performing_modules:
        observations.append(LearningObservation("dashboard", module.module, "underperformer", module.hit_rate, _confidence(module.confidence_accuracy, module.appearances), f"{module.module} is a dashboard underperformer."))
    return observations


def _insights(
    observations: Sequence[LearningObservation],
    *,
    dashboard: CalibrationDashboard | None,
    trend_summary: TrendSummary | None,
) -> list[LearningInsight]:
    insights: list[LearningInsight] = []
    strong = _subjects_by_metric(observations, minimum=0.60)
    weak = _subjects_by_metric(observations, maximum=0.25)
    for subject in strong:
        insights.append(
            LearningInsight(
                category="consistent_strength",
                subject=subject,
                summary=f"{subject} appears as a consistent strength across learning inputs.",
                confidence=_subject_confidence(observations, subject),
                supporting_observations=_supporting(observations, subject),
            )
        )
    for subject in weak:
        insights.append(
            LearningInsight(
                category="consistent_weakness",
                subject=subject,
                summary=f"{subject} appears as a consistent weakness or review candidate.",
                confidence=_subject_confidence(observations, subject),
                supporting_observations=_supporting(observations, subject),
            )
        )
    if trend_summary:
        for module in trend_summary.heating_up:
            insights.append(LearningInsight("emerging_trend", module, f"{module} is heating up in trend summaries.", 0.75, _supporting(observations, module)))
        for module in trend_summary.cooling_off:
            insights.append(LearningInsight("consistent_weakness", module, f"{module} is cooling off in trend summaries.", 0.75, _supporting(observations, module)))
    if dashboard:
        for text in dashboard.portfolio_summaries + dashboard.diversification_summaries + dashboard.simulation_summaries:
            insights.append(LearningInsight("operator_context", "Operator Summary", text, 0.6, [text]))
    return _unique_insights(insights)


def _recommendations(
    observations: Sequence[LearningObservation],
    insights: Sequence[LearningInsight],
    *,
    simulation_result: SimulationResult | None,
    recommendation_report: RecommendationReport | None,
    optimizer_result: OptimizationResult | None,
) -> list[LearningRecommendation]:
    recommendations: list[LearningRecommendation] = []
    for insight in insights:
        if insight.category == "consistent_strength":
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.THRESHOLD_REVIEW,
                    subject=insight.subject,
                    action="Review whether current thresholds are correctly capturing this strength.",
                    confidence=insight.confidence,
                    reasoning=insight.summary,
                    supporting_insights=[insight.summary],
                )
            )
        if insight.category == "consistent_weakness":
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.THRESHOLD_REVIEW,
                    subject=insight.subject,
                    action="Review thresholds and validation inputs before considering formula changes.",
                    confidence=insight.confidence,
                    reasoning=insight.summary,
                    supporting_insights=[insight.summary],
                )
            )
    if recommendation_report:
        for item in recommendation_report.modules:
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.WEIGHT_REVIEW,
                    subject=item.module,
                    action="Review weight recommendation manually; do not auto-apply.",
                    confidence=_confidence_label(item.confidence),
                    reasoning=item.reasoning or f"Suggested weight {item.suggested_weight} from current {item.current_weight}.",
                    supporting_insights=[item.trend_direction],
                )
            )
    if optimizer_result:
        for scenario in optimizer_result.scenarios:
            if scenario.rejected:
                continue
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.WEIGHT_REVIEW,
                    subject=scenario.module,
                    action="Review optimizer scenario manually; do not auto-apply.",
                    confidence=_confidence_label(scenario.confidence_level),
                    reasoning=scenario.reasoning,
                    supporting_insights=[scenario.recommendation],
                )
            )
    if simulation_result and simulation_result.summary:
        if simulation_result.summary.risk_grade.value in {"HIGH", "EXTREME"}:
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.PORTFOLIO_REVIEW,
                    subject="Portfolio",
                    action="Review exposure, volatility, and drawdown before using this portfolio shape.",
                    confidence=0.85,
                    reasoning=f"Simulation risk grade is {simulation_result.summary.risk_grade.value}.",
                    supporting_insights=[f"Drawdown risk {simulation_result.summary.drawdown_risk:.1%}."],
                )
            )
        if simulation_result.summary.drawdown_risk > 0.35:
            recommendations.append(
                LearningRecommendation(
                    recommendation_type=LearningRecommendationType.DIVERSIFICATION_REVIEW,
                    subject="Portfolio",
                    action="Review diversification before adding additional correlated slips.",
                    confidence=0.8,
                    reasoning="Monte Carlo drawdown risk is elevated.",
                    supporting_insights=[f"Drawdown risk {simulation_result.summary.drawdown_risk:.1%}."],
                )
            )
    if not recommendations and observations:
        recommendations.append(
            LearningRecommendation(
                recommendation_type=LearningRecommendationType.VALIDATION_REVIEW,
                subject="Learning Inputs",
                action="Continue collecting history before making tuning decisions.",
                confidence=0.55,
                reasoning="Learning inputs are present but not strong enough for a specific recommendation.",
            )
        )
    return sorted(_unique_recommendations(recommendations), key=lambda item: item.confidence, reverse=True)


def _top_modules(observations: Sequence[LearningObservation], dashboard: CalibrationDashboard | None) -> list[str]:
    if dashboard and dashboard.top_performing_modules:
        return [module.module for module in dashboard.top_performing_modules]
    return _subjects_by_metric(observations, minimum=0.60)[:5]


def _weak_modules(observations: Sequence[LearningObservation], dashboard: CalibrationDashboard | None) -> list[str]:
    if dashboard and dashboard.worst_performing_modules:
        return [module.module for module in dashboard.worst_performing_modules]
    return _subjects_by_metric(observations, maximum=0.25)[:5]


def _subjects_by_metric(
    observations: Sequence[LearningObservation],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> list[str]:
    subjects: list[str] = []
    for observation in observations:
        if not isinstance(observation.value, (int, float)):
            continue
        if observation.subject == "Portfolio":
            continue
        if minimum is not None and observation.value >= minimum:
            subjects.append(observation.subject)
        if maximum is not None and observation.value <= maximum:
            subjects.append(observation.subject)
    return _unique(subjects)


def _supporting(observations: Sequence[LearningObservation], subject: str) -> list[str]:
    return [observation.summary for observation in observations if observation.subject == subject][:5]


def _subject_confidence(observations: Sequence[LearningObservation], subject: str) -> float:
    values = [observation.confidence for observation in observations if observation.subject == subject]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _confidence(value: float, sample_size: int) -> float:
    sample = min(1.0, max(sample_size, 0) / 100.0)
    return round(max(0.0, min(1.0, abs(value) * 0.55 + sample * 0.45)), 4)


def _confidence_label(value: str) -> float:
    normalized = str(value).strip().lower()
    if normalized in {"elite", "high", "strong"}:
        return 0.9
    if normalized in {"medium", "moderate"}:
        return 0.65
    if normalized in {"low", "weak"}:
        return 0.35
    return 0.5


def _unique(values: Sequence[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _unique_insights(insights: Sequence[LearningInsight]) -> list[LearningInsight]:
    seen = set()
    output = []
    for insight in insights:
        key = (insight.category, insight.subject, insight.summary)
        if key not in seen:
            seen.add(key)
            output.append(insight)
    return output


def _unique_recommendations(recommendations: Sequence[LearningRecommendation]) -> list[LearningRecommendation]:
    seen = set()
    output = []
    for recommendation in recommendations:
        key = (recommendation.recommendation_type, recommendation.subject, recommendation.action)
        if key not in seen:
            seen.add(key)
            output.append(recommendation)
    return output


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
