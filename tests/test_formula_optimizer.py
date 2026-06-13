import json
from dataclasses import is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.backtesting import BacktestRequest, BacktestResult, BacktestSummary, HistoricalBacktestEngine
from russworks.calibration import CalibrationMetric, CalibrationResult, FormulaCalibrationEngine
from russworks.dashboard import CalibrationDashboard, CalibrationDashboardEngine, ModulePerformance
from russworks.optimizer import FormulaOptimizer, OptimizationResult, OptimizationScenario, optimize_formula
from russworks.recommendations import ModuleRecommendation, RecommendationReport, WeightRecommendationEngine
from russworks.trends import TrendEngine, TrendMetric, TrendSummary


MODULES = [
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


def test_phase25_optimizer_models_are_dataclasses():
    assert is_dataclass(OptimizationScenario)
    assert is_dataclass(OptimizationResult)


def test_optimizer_evaluates_all_modules_and_simulates_weight_changes():
    calibration = CalibrationResult(
        metrics=[
            CalibrationMetric("TAG", 40, 16, 0.4, 12, 2, 0.72),
            CalibrationMetric("CPS", 40, 4, 0.1, 34, 6, 0.5),
            CalibrationMetric("Umpire", 20, 5, 0.25, 8, 1, 0.1),
            CalibrationMetric("Pitch Mix", 30, 9, 0.3, 10, 1, 0.6),
            CalibrationMetric("Park Factor", 30, 8, 0.2667, 12, 2, 0.52),
        ]
    )
    trends = TrendSummary(
        generated_at="2026-06-13T00:00:00Z",
        metrics=[
            TrendMetric("TAG", 0.45, 0.42, 0.40, 0.35, "Heating Up", 40),
            TrendMetric("CPS", 0.08, 0.10, 0.12, 0.18, "Cooling Off", 40),
            TrendMetric("Pitch Mix Matchup", 0.36, 0.34, 0.31, 0.28, "Heating Up", 30),
        ],
    )

    result = optimize_formula(calibration_result=calibration, trend_summary=trends)

    assert result.success
    assert [scenario.module for scenario in result.scenarios] == MODULES
    tag = _find(result.scenarios, "TAG")
    cps = _find(result.scenarios, "CPS")
    umpire = _find(result.scenarios, "Umpire")
    pitch_mix = _find(result.scenarios, "Pitch Mix Matchup")

    assert tag.recommendation == "increase"
    assert tag.simulated_weight > tag.current_weight
    assert tag.expected_impact > 0
    assert cps.recommendation == "decrease"
    assert cps.simulated_weight < cps.current_weight
    assert cps.expected_impact < 0
    assert umpire.rejected
    assert umpire.recommendation == "hold"
    assert pitch_mix.recommendation == "increase"
    assert all(scenario.reasoning for scenario in result.scenarios)
    assert "Live weights were not modified." in result.summaries


def test_optimizer_rejects_missing_low_sample_and_noisy_data():
    calibration = CalibrationResult(
        metrics=[
            CalibrationMetric("YPI", 4, 2, 0.5, 1, 0, 0.7),
            CalibrationMetric("Veteran Bounce", 20, 4, 0.2, 10, 2, 0.1),
        ]
    )

    result = FormulaOptimizer().optimize(calibration_result=calibration)

    ypi = _find(result.scenarios, "YPI")
    veteran = _find(result.scenarios, "Veteran Bounce")
    tag = _find(result.scenarios, "TAG")

    assert ypi.rejected
    assert "at least 10" in ypi.reasoning
    assert veteran.rejected
    assert "noise threshold" in veteran.reasoning
    assert tag.rejected
    assert tag.supporting_metrics["source"] == "none"


def test_optimizer_uses_dashboard_recommendation_trend_and_backtest_inputs():
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModulePerformance("Bullpen Exposure", 30, 11, 19, 0.3667, 9, 1, 0.62),
        ],
    )
    recommendations = RecommendationReport(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModuleRecommendation(
                module="Park Factor V2",
                current_weight=1.0,
                suggested_weight=1.1,
                confidence="medium",
                trend_direction="increase",
                supporting_metrics={"appearances": 25, "hit_rate": 0.32, "source": "recommendations"},
                reasoning="Park Factor is strengthening.",
            )
        ],
    )
    trends = TrendSummary(
        generated_at="2026-06-13T00:00:00Z",
        metrics=[TrendMetric("Park Factor V2", 0.38, 0.36, 0.33, 0.28, "Heating Up", 25)],
    )
    backtest = BacktestResult(
        request=BacktestRequest("2026-06-01", "2026-06-02"),
        summary=BacktestSummary(
            start_date="2026-06-01",
            end_date="2026-06-02",
            dates_tested=2,
            total_games=4,
            total_batters_reviewed=50,
            total_hrs_hit=12,
            step3_hits=8,
            step4_hits=7,
            step5_hits=5,
            non_superstar_hits=3,
            ypi_hits=6,
            veteran_hits=2,
            catcher_hits=4,
            weak_spot_hits=5,
            pitch_mix_hits=6,
            step3_hit_rate=0.6667,
            step4_hit_rate=0.5833,
            step5_hit_rate=0.4167,
            non_superstar_hit_rate=0.25,
            ypi_hit_rate=0.5,
            veteran_hit_rate=0.1667,
            catcher_hit_rate=0.3333,
            weak_spot_hit_rate=0.4167,
            pitch_mix_hit_rate=0.5,
        ),
    )

    result = FormulaOptimizer().optimize(
        dashboard=dashboard,
        recommendation_report=recommendations,
        trend_summary=trends,
        backtest_result=backtest,
    )

    assert _find(result.scenarios, "Bullpen Exposure").supporting_metrics["source"] == "dashboard"
    assert "recommendations" in _find(result.scenarios, "Park Factor V2").supporting_metrics["source"]
    assert _find(result.scenarios, "YPI").supporting_metrics["source"] == "backtest"


def test_optimizer_export_writes_optimizer_report_json():
    result = FormulaOptimizer().optimize(
        calibration_result=CalibrationResult(metrics=[CalibrationMetric("TAG", 20, 8, 0.4, 6, 1, 0.7)])
    )

    with TemporaryDirectory() as temp_dir:
        output = FormulaOptimizer().export_json(result, temp_dir)

        assert output == Path(temp_dir) / "optimizer_report.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["scenarios"][0]["module"] == "TAG"


def test_optimizer_integration_methods_are_available():
    calibration = CalibrationResult(metrics=[CalibrationMetric("TAG", 20, 8, 0.4, 6, 1, 0.7)])
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[ModulePerformance("CPS", 20, 4, 16, 0.2, 12, 2, 0.45)],
    )
    recommendations = RecommendationReport(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModuleRecommendation(
                module="LSTM",
                current_weight=1.0,
                suggested_weight=1.0,
                confidence="medium",
                trend_direction="hold",
                supporting_metrics={"appearances": 20, "hit_rate": 0.25},
                reasoning="Hold.",
            )
        ],
    )
    trends = TrendSummary(
        generated_at="2026-06-13T00:00:00Z",
        metrics=[TrendMetric("YPI", 0.4, 0.35, 0.3, 0.25, "Heating Up", 20)],
    )
    backtest = BacktestResult(
        request=BacktestRequest("2026-06-01", "2026-06-01"),
        summary=BacktestSummary(
            start_date="2026-06-01",
            end_date="2026-06-01",
            dates_tested=1,
            total_games=2,
            total_batters_reviewed=20,
            total_hrs_hit=5,
            step3_hits=3,
            step4_hits=3,
            step5_hits=2,
            non_superstar_hits=1,
            ypi_hits=3,
            veteran_hits=1,
            catcher_hits=1,
            weak_spot_hits=2,
            pitch_mix_hits=3,
            step3_hit_rate=0.6,
            step4_hit_rate=0.6,
            step5_hit_rate=0.4,
            non_superstar_hit_rate=0.2,
            ypi_hit_rate=0.6,
            veteran_hit_rate=0.2,
            catcher_hit_rate=0.2,
            weak_spot_hit_rate=0.4,
            pitch_mix_hit_rate=0.6,
        ),
    )

    from_calibration = FormulaCalibrationEngine().build_optimizer(calibration)
    from_dashboard = CalibrationDashboardEngine().build_optimizer(dashboard)
    from_recommendations = WeightRecommendationEngine().build_optimizer(recommendations)
    from_trends = TrendEngine().build_optimizer(trends)
    from_backtest = HistoricalBacktestEngine().build_optimizer(backtest)

    assert _find(from_calibration.scenarios, "TAG").supporting_metrics["source"] == "calibration"
    assert _find(from_dashboard.scenarios, "CPS").supporting_metrics["source"] == "dashboard"
    assert _find(from_recommendations.scenarios, "LSTM").supporting_metrics["source"] == "recommendations"
    assert _find(from_trends.scenarios, "YPI").supporting_metrics["source"] == "trends"
    assert _find(from_backtest.scenarios, "Pitch Mix Matchup").supporting_metrics["source"] == "backtest"


def test_empty_optimizer_result_reports_missing_inputs():
    result = FormulaOptimizer().optimize()

    assert not result.success
    assert result.errors == ["Formula optimization requires calibration, dashboard, recommendation, trend, or backtest metrics."]
    assert len(result.scenarios) == len(MODULES)
    assert all(scenario.rejected for scenario in result.scenarios)


def _find(scenarios, module):
    for scenario in scenarios:
        if scenario.module == module:
            return scenario
    raise AssertionError(f"Missing scenario for {module}")
