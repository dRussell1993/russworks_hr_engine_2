import json
from dataclasses import is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.backtesting import BacktestRequest, BacktestResult, DailyBacktestSummary
from russworks.calibration import CalibrationMetric, CalibrationResult, FormulaCalibrationEngine
from russworks.dashboard import CalibrationDashboard, CalibrationDashboardEngine, ModulePerformance
from russworks.recommendations import ModuleRecommendation, RecommendationReport, WeightRecommendationEngine
from russworks.trends import TrendEngine, TrendMetric, TrendSummary, build_trends


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


def test_phase24_trend_models_are_dataclasses():
    assert is_dataclass(TrendMetric)
    assert is_dataclass(TrendSummary)


def test_trend_engine_tracks_all_modules_and_classifies_daily_windows():
    backtest = BacktestResult(
        request=BacktestRequest(start_date="2026-05-10", end_date="2026-06-13"),
        daily_summaries=_daily_summaries(),
    )
    calibration = CalibrationResult(
        metrics=[
            CalibrationMetric("TAG", 40, 12, 0.3, 10, 2, 0.6),
            CalibrationMetric("CPS", 40, 10, 0.25, 12, 3, 0.55),
            CalibrationMetric("Pitch Mix", 20, 4, 0.2, 10, 2, 0.4),
            CalibrationMetric("Park Factor", 20, 5, 0.25, 8, 2, 0.45),
        ]
    )

    summary = build_trends(backtest_result=backtest, calibration_result=calibration)

    assert summary.success
    assert [metric.module for metric in summary.metrics] == MODULES
    ypi = _find(summary.metrics, "YPI")
    veteran = _find(summary.metrics, "Veteran Bounce")
    catcher = _find(summary.metrics, "Catcher Power")
    tag = _find(summary.metrics, "TAG")

    assert ypi.seven_day_trend > ypi.season_trend
    assert ypi.classification == "Heating Up"
    assert veteran.seven_day_trend < veteran.season_trend
    assert veteran.classification == "Cooling Off"
    assert catcher.classification == "Stable"
    assert tag.classification == "Stable"
    assert tag.supporting_metrics["source"] == "calibration"
    assert "YPI" in summary.heating_up
    assert "Veteran Bounce" in summary.cooling_off


def test_trend_engine_uses_dashboard_and_recommendation_snapshots():
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModulePerformance(
                module="Bullpen Exposure",
                appearances=30,
                wins=9,
                losses=21,
                hit_rate=0.3,
                false_positives=12,
                false_negatives=2,
                confidence_accuracy=0.55,
            )
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
                supporting_metrics={"appearances": 20, "hit_rate": 0.35, "source": "recommendations"},
                reasoning="Park Factor V2 is improving.",
            )
        ],
    )

    summary = TrendEngine().build_trends(dashboard=dashboard, recommendation_report=recommendations)

    assert _find(summary.metrics, "Bullpen Exposure").supporting_metrics["source"] == "dashboard"
    assert _find(summary.metrics, "Park Factor V2").supporting_metrics["source"] == "recommendations"


def test_trend_export_writes_trends_json():
    summary = TrendEngine().build_trends(calibration_result=CalibrationResult(metrics=[CalibrationMetric("TAG", 12, 4, 0.3333, 5, 1, 0.6)]))

    with TemporaryDirectory() as temp_dir:
        output = TrendEngine().export_json(summary, temp_dir)

        assert output == Path(temp_dir) / "trends.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["metrics"][0]["module"] == "TAG"


def test_integrations_build_trends_from_dashboard_calibration_and_recommendations():
    calibration = CalibrationResult(metrics=[CalibrationMetric("TAG", 20, 7, 0.35, 6, 1, 0.65)])
    dashboard = CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModulePerformance(
                module="CPS",
                appearances=20,
                wins=5,
                losses=15,
                hit_rate=0.25,
                false_positives=9,
                false_negatives=1,
                confidence_accuracy=0.5,
            )
        ],
    )
    recommendations = RecommendationReport(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModuleRecommendation(
                module="LSTM",
                current_weight=1.0,
                suggested_weight=1.0,
                confidence="low",
                trend_direction="hold",
                supporting_metrics={"appearances": 18, "hit_rate": 0.22, "source": "recommendations"},
                reasoning="Hold.",
            )
        ],
    )

    from_calibration = FormulaCalibrationEngine().build_trends(calibration)
    from_dashboard = CalibrationDashboardEngine().build_trends(dashboard)
    from_recommendations = WeightRecommendationEngine().build_trends(recommendations)

    assert _find(from_calibration.metrics, "TAG").supporting_metrics["source"] == "calibration"
    assert _find(from_dashboard.metrics, "CPS").supporting_metrics["source"] == "dashboard"
    assert _find(from_recommendations.metrics, "LSTM").supporting_metrics["source"] == "recommendations"


def test_empty_trend_summary_reports_missing_inputs():
    summary = TrendEngine().build_trends()

    assert not summary.success
    assert summary.errors == ["Trend engine requires dashboard, calibration, recommendation, or backtest metrics."]
    assert len(summary.metrics) == len(MODULES)


def _daily_summaries():
    summaries = []
    for index in range(35):
        late_window = index >= 28
        summaries.append(
            DailyBacktestSummary(
                date=f"2026-05-{10 + index:02d}" if index < 22 else f"2026-06-{index - 21:02d}",
                games_reviewed=1,
                total_batters_reviewed=10,
                total_hrs_hit=5,
                step3_hits=3,
                step4_hits=3,
                step5_hits=2,
                non_superstar_hits=1,
                ypi_hits=5 if late_window else 1,
                veteran_hits=1 if late_window else 5,
                catcher_hits=2,
                weak_spot_hits=3 if late_window else 2,
                pitch_mix_hits=4 if late_window else 2,
                step3_hit_rate=0.6,
                step4_hit_rate=0.6,
                step5_hit_rate=0.4,
                non_superstar_hit_rate=0.2,
                ypi_hit_rate=0.5 if late_window else 0.1,
                veteran_hit_rate=0.1 if late_window else 0.5,
                catcher_hit_rate=0.2,
                weak_spot_hit_rate=0.3 if late_window else 0.2,
                pitch_mix_hit_rate=0.4 if late_window else 0.2,
            )
        )
    return summaries


def _find(metrics, module):
    for metric in metrics:
        if metric.module == module:
            return metric
    raise AssertionError(f"Missing metric for {module}")
