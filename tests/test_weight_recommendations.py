import json
import tempfile

from russworks.backtesting import (
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
    HistoricalBacktestEngine,
)
from russworks.calibration import CalibrationMetric, CalibrationResult, FormulaCalibrationEngine
from russworks.dashboard import CalibrationDashboard, CalibrationDashboardEngine, ModulePerformance
from russworks.recommendations import WeightRecommendationEngine, build_weight_recommendations


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


def test_weight_recommendations_cover_all_tracked_modules():
    result = CalibrationResult(
        metrics=[
            CalibrationMetric("TAG", 40, 16, 0.4, 12, 2, 0.72),
            CalibrationMetric("CPS", 40, 4, 0.1, 34, 6, 0.5),
            CalibrationMetric("Pitch Mix", 30, 10, 0.3333, 9, 1, 0.6),
            CalibrationMetric("Park Factor", 30, 8, 0.2667, 12, 2, 0.52),
            CalibrationMetric("YPI", 4, 2, 0.5, 1, 0, 0.7),
            CalibrationMetric("Umpire", 20, 5, 0.25, 8, 1, 0.1),
        ]
    )

    report = build_weight_recommendations(calibration_result=result)

    assert [item.module for item in report.modules] == MODULES
    tag = _find(report.modules, "TAG")
    cps = _find(report.modules, "CPS")
    pitch_mix = _find(report.modules, "Pitch Mix Matchup")
    ypi = _find(report.modules, "YPI")
    umpire = _find(report.modules, "Umpire")

    assert tag.trend_direction == "increase"
    assert tag.suggested_weight > tag.current_weight
    assert cps.trend_direction == "decrease"
    assert cps.suggested_weight < cps.current_weight
    assert pitch_mix.supporting_metrics["source"] == "calibration"
    assert ypi.trend_direction == "insufficient_sample"
    assert ypi.suggested_weight == ypi.current_weight
    assert umpire.trend_direction == "noisy"
    assert umpire.suggested_weight == umpire.current_weight
    assert all(item.reasoning for item in report.modules)
    assert all(item.recommendation is not None and item.recommendation.applied is False for item in report.modules)


def test_dashboard_metrics_can_drive_recommendations_and_export_json():
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModulePerformance(
                module="Bullpen Exposure",
                appearances=24,
                wins=10,
                losses=14,
                hit_rate=0.4167,
                false_positives=8,
                false_negatives=1,
                confidence_accuracy=0.66,
            )
        ],
    )
    engine = WeightRecommendationEngine()

    report = engine.build_recommendations(dashboard=dashboard, current_weights={"Bullpen Exposure": 2.0})
    bullpen = _find(report.modules, "Bullpen Exposure")

    assert bullpen.current_weight == 2.0
    assert bullpen.trend_direction == "increase"
    assert bullpen.supporting_metrics["source"] == "dashboard"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = engine.export_json(report, tmpdir)
        assert output_path.name == "recommendations.json"
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["modules"][0]["module"] == "TAG"


def test_empty_recommendation_report_requires_metrics_and_holds_weights():
    report = WeightRecommendationEngine().build_recommendations()

    assert report.errors == ["Weight recommendations require calibration, dashboard, or backtest metrics."]
    assert len(report.modules) == len(MODULES)
    assert all(item.trend_direction == "insufficient_sample" for item in report.modules)
    assert all(item.current_weight == item.suggested_weight for item in report.modules)


def test_existing_engines_expose_weight_recommendation_integration():
    calibration = CalibrationResult(
        metrics=[CalibrationMetric("TAG", 30, 12, 0.4, 8, 1, 0.7)]
    )
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModulePerformance(
                module="Catcher Power",
                appearances=30,
                wins=11,
                losses=19,
                hit_rate=0.3667,
                false_positives=10,
                false_negatives=2,
                confidence_accuracy=0.62,
            )
        ],
    )
    backtest = BacktestResult(
        request=BacktestRequest(start_date="2026-06-01", end_date="2026-06-02"),
        summary=BacktestSummary(
            start_date="2026-06-01",
            end_date="2026-06-02",
            dates_tested=2,
            total_games=4,
            total_batters_reviewed=60,
            total_hrs_hit=14,
            step3_hits=8,
            step4_hits=7,
            step5_hits=5,
            non_superstar_hits=3,
            ypi_hits=4,
            veteran_hits=2,
            catcher_hits=5,
            weak_spot_hits=3,
            pitch_mix_hits=6,
            step3_hit_rate=0.5714,
            step4_hit_rate=0.5,
            step5_hit_rate=0.3571,
            non_superstar_hit_rate=0.2143,
            ypi_hit_rate=0.2857,
            veteran_hit_rate=0.1429,
            catcher_hit_rate=0.3571,
            weak_spot_hit_rate=0.2143,
            pitch_mix_hit_rate=0.4286,
        ),
    )

    from_calibration = FormulaCalibrationEngine().build_weight_recommendations(calibration)
    from_dashboard = CalibrationDashboardEngine().build_weight_recommendations(dashboard)
    from_backtest = HistoricalBacktestEngine().build_weight_recommendations(backtest)

    assert _find(from_calibration.modules, "TAG").trend_direction == "increase"
    assert _find(from_dashboard.modules, "Catcher Power").supporting_metrics["source"] == "dashboard"
    assert _find(from_backtest.modules, "Pitch Mix Matchup").supporting_metrics["source"] == "backtest"


def _find(recommendations, module):
    for recommendation in recommendations:
        if recommendation.module == module:
            return recommendation
    raise AssertionError(f"Missing recommendation for {module}")
