from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.backtesting import BacktestRequest, BacktestResult, BacktestSummary
from russworks.calibration import CalibrationMetric, CalibrationRecommendation, CalibrationResult
from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.explainability import ExplainabilityEngine
from russworks.optimizer import OptimizationResult, OptimizationScenario
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.recommendations import ModuleRecommendation, RecommendationReport
from russworks.self_learning import (
    LearningInsight,
    LearningObservation,
    LearningRecommendation,
    LearningSummary,
    SelfLearningEngine,
    SelfLearningReport,
)
from russworks.simulation import MonteCarloEngine
from russworks.trends import TrendMetric, TrendSummary

from tests.test_daily_pipeline import _slate
from tests.test_simulation_engine import _slip


DATE = "2026-06-13"


def _calibration_result() -> CalibrationResult:
    metrics = [
        CalibrationMetric("TAG", 120, 82, 0.6833, 10, 4, 0.82),
        CalibrationMetric("Umpire", 120, 18, 0.15, 42, 22, 0.31),
    ]
    return CalibrationResult(
        metrics=metrics,
        strength_rankings=[metrics[0]],
        weakness_rankings=[metrics[1]],
        recommended_adjustments=[
            CalibrationRecommendation("Umpire", "decrease", -0.05, "High", "Umpire has persistent false positives."),
        ],
    )


def _backtest_result() -> BacktestResult:
    summary = BacktestSummary(
        start_date="2026-06-01",
        end_date=DATE,
        dates_tested=13,
        total_games=26,
        total_batters_reviewed=240,
        total_hrs_hit=48,
        step3_hits=40,
        step4_hits=34,
        step5_hits=21,
        non_superstar_hits=8,
        ypi_hits=9,
        veteran_hits=7,
        catcher_hits=3,
        weak_spot_hits=14,
        pitch_mix_hits=18,
        step3_hit_rate=0.8333,
        step4_hit_rate=0.7083,
        step5_hit_rate=0.4375,
        non_superstar_hit_rate=0.1667,
        ypi_hit_rate=0.1875,
        veteran_hit_rate=0.1458,
        catcher_hit_rate=0.0625,
        weak_spot_hit_rate=0.2917,
        pitch_mix_hit_rate=0.375,
    )
    return BacktestResult(request=BacktestRequest("2026-06-01", DATE), summary=summary)


def _trend_summary() -> TrendSummary:
    return TrendSummary(
        generated_at="2026-06-13T00:00:00Z",
        metrics=[
            TrendMetric("TAG", 0.72, 0.69, 0.66, 0.64, "Heating Up", 120),
            TrendMetric("Umpire", 0.18, 0.2, 0.21, 0.19, "Cooling Off", 120),
        ],
        heating_up=["TAG"],
        cooling_off=["Umpire"],
    )


def _optimizer_result() -> OptimizationResult:
    return OptimizationResult(
        generated_at="2026-06-13T00:00:00Z",
        scenarios=[
            OptimizationScenario("TAG", 1.0, 1.05, 0.05, 0.68, 0.08, "High", "review increase", False, "TAG shows durable performance."),
        ],
    )


def _recommendation_report() -> RecommendationReport:
    return RecommendationReport(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModuleRecommendation("TAG", 1.0, 1.05, "High", "up", {"appearances": 120}, "TAG has strong supporting metrics."),
        ],
    )


def _simulation_result():
    slips = [_slip("one", "TEX"), _slip("two", "KC", "balanced")]
    return MonteCarloEngine().simulate_portfolio(slips)


def test_phase35_self_learning_models_are_dataclasses():
    assert is_dataclass(LearningObservation)
    assert is_dataclass(LearningInsight)
    assert is_dataclass(LearningRecommendation)
    assert is_dataclass(LearningSummary)
    assert is_dataclass(SelfLearningReport)


def test_self_learning_engine_generates_confidence_ranked_recommendations_and_exports_json():
    engine = SelfLearningEngine()
    report = engine.build_report(
        calibration_result=_calibration_result(),
        backtest_result=_backtest_result(),
        trend_summary=_trend_summary(),
        optimizer_result=_optimizer_result(),
        simulation_result=_simulation_result(),
        recommendation_report=_recommendation_report(),
    )

    assert report.success
    assert "TAG" in report.summary.top_performing_modules
    assert "Umpire" in report.summary.underperforming_modules
    assert report.summary.confidence_ranked_recommendations
    assert report.summary.confidence_ranked_recommendations[0].confidence >= report.summary.confidence_ranked_recommendations[-1].confidence

    with TemporaryDirectory() as temp_dir:
        output_path = engine.export_json(report, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "self_learning_report.json"
    assert payload["summary"]["top_performing_modules"]


def test_daily_pipeline_exports_self_learning_report_and_full_report_section():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, request)

        assert result.success
        assert result.self_learning_report is not None
        assert result.self_learning_report_path == str(output_root.parent / "self_learning" / "self_learning_report.json")
        assert Path(result.self_learning_report_path).exists()

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))
        assert payload["self_learning"]["notes"]
        assert "self_learning_context" in payload["explanations"]


def test_dashboard_command_center_and_explainability_surface_self_learning_context():
    report = SelfLearningEngine().build_report(
        calibration_result=_calibration_result(),
        trend_summary=_trend_summary(),
        optimizer_result=_optimizer_result(),
        simulation_result=_simulation_result(),
        recommendation_report=_recommendation_report(),
    )
    pipeline_result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))

    dashboard = CalibrationDashboardEngine().build_dashboard(self_learning_report=report)
    command_center = CommandCenterEngine().build_report(daily_run_result=pipeline_result)
    explanations = ExplainabilityEngine().generate_explanations(self_learning_report=report)

    assert dashboard.self_learning_summaries
    assert command_center.formula_health.self_learning_summary["recommendation_count"] >= 1
    assert pipeline_result.self_learning_report_path in command_center.execution_summary.exports_generated
    assert explanations["self_learning_context"]["recommendations"]
