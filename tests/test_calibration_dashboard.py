from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.backtesting import (
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
    DailyBacktestSummary,
    HistoricalBacktestEngine,
)
from russworks.calibration import CalibrationMetric, CalibrationResult, FormulaCalibrationEngine
from russworks.dashboard import (
    ArchetypePerformance,
    CalibrationDashboard,
    CalibrationDashboardEngine,
    ModulePerformance,
    TrendReport,
    build_calibration_dashboard,
)
from russworks.postmortem import (
    FalsePositiveEntry,
    LoserLogEntry,
    PostMortemEngine,
    PostMortemReport,
    WinnerLogEntry,
)


def _calibration_result() -> CalibrationResult:
    metrics = [
        CalibrationMetric("TAG", 20, 8, 0.4, 12, 2, 0.62),
        CalibrationMetric("CPS", 18, 7, 0.3889, 11, 2, 0.59),
        CalibrationMetric("LSTM", 16, 5, 0.3125, 11, 3, 0.45),
        CalibrationMetric("PVS", 15, 6, 0.4, 9, 2, 0.58),
        CalibrationMetric("Environment", 14, 4, 0.2857, 10, 4, 0.38),
        CalibrationMetric("Umpire", 10, 3, 0.3, 7, 4, 0.32),
        CalibrationMetric("Weak Spot Collision", 8, 5, 0.625, 3, 1, 0.72),
        CalibrationMetric("YPI", 6, 4, 0.6667, 2, 1, 0.71),
        CalibrationMetric("Veteran Bounce", 7, 3, 0.4286, 4, 1, 0.49),
        CalibrationMetric("Catcher Power", 5, 2, 0.4, 3, 1, 0.43),
        CalibrationMetric("Pitch Mix", 9, 5, 0.5556, 4, 1, 0.67),
        CalibrationMetric("Bullpen Exposure", 8, 3, 0.375, 5, 2, 0.40),
        CalibrationMetric("Park Factor", 6, 2, 0.3333, 4, 2, 0.35),
    ]
    return CalibrationResult(
        metrics=metrics,
        strength_rankings=sorted(metrics, key=lambda item: item.confidence_score, reverse=True),
        weakness_rankings=sorted(metrics, key=lambda item: item.confidence_score),
        trend_summaries=["Strongest module: Weak Spot Collision"],
    )


def _postmortem_report() -> PostMortemReport:
    return PostMortemReport(
        winner_log=[
            WinnerLogEntry("TEX", "YPI Winner", "slider", "KC Starter", 2, 106.0, 408.0, 27.0, archetypes=["YPI", "Weak Spot Collision"]),
            WinnerLogEntry("KC", "Veteran Winner", "fastball", "TEX Starter", 5, 104.0, 401.0, 25.0, archetypes=["Veteran Bounce", "Pitch Mix"]),
        ],
        loser_log=[
            LoserLogEntry("TEX", "Catcher Miss", "Slip", "chaos", "A", "A", 92.0, "chaos", archetypes=["Catcher Power"]),
            LoserLogEntry("SEA", "Park Miss", "Slip", "core", "B", "B", 72.0, "core", archetypes=["Park Factor"]),
        ],
        false_positive_log=[
            FalsePositiveEntry("TEX", "Catcher Miss", "Slip", "chaos", "High-confidence miss.", ["Catcher Power"]),
        ],
    )


def _backtest_result() -> BacktestResult:
    daily = [
        DailyBacktestSummary("2026-06-12", 1, 18, 2, 2, 2, 1, 1, 1, 0, 1, 2, 1, 1.0, 1.0, 0.5, 0.5, 0.5, 0.0, 0.5, 1.0, 0.5),
        DailyBacktestSummary("2026-06-13", 1, 18, 2, 2, 2, 2, 1, 1, 1, 0, 1, 2, 1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.0, 0.5, 1.0),
    ]
    summary = BacktestSummary(
        start_date="2026-06-12",
        end_date="2026-06-13",
        dates_tested=2,
        total_games=2,
        total_batters_reviewed=36,
        total_hrs_hit=4,
        step3_hits=4,
        step4_hits=4,
        step5_hits=3,
        non_superstar_hits=2,
        ypi_hits=2,
        veteran_hits=1,
        catcher_hits=1,
        weak_spot_hits=3,
        pitch_mix_hits=2,
        step3_hit_rate=1.0,
        step4_hit_rate=1.0,
        step5_hit_rate=0.75,
        non_superstar_hit_rate=0.5,
        ypi_hit_rate=0.5,
        veteran_hit_rate=0.25,
        catcher_hit_rate=0.25,
        weak_spot_hit_rate=0.75,
        pitch_mix_hit_rate=0.5,
    )
    return BacktestResult(request=BacktestRequest("2026-06-12", "2026-06-13"), daily_summaries=daily, summary=summary)


def test_phase21_dashboard_models_are_dataclasses():
    assert is_dataclass(CalibrationDashboard)
    assert is_dataclass(ModulePerformance)
    assert is_dataclass(TrendReport)
    assert is_dataclass(ArchetypePerformance)


def test_dashboard_tracks_all_required_module_performance():
    dashboard = build_calibration_dashboard(
        _calibration_result(),
        postmortem_reports=[_postmortem_report()],
        backtest_result=_backtest_result(),
    )
    modules = {module.module: module for module in dashboard.modules}

    expected = {
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
    }
    assert set(modules) == expected
    assert modules["TAG"].wins == 8
    assert modules["Pitch Mix Matchup"].hit_rate == 0.5556
    assert modules["Park Factor V2"].false_positives == 4


def test_dashboard_generates_rankings_trends_and_archetype_success_rates():
    dashboard = CalibrationDashboardEngine().build_dashboard(
        calibration_result=_calibration_result(),
        postmortem_reports=[_postmortem_report()],
        backtest_result=_backtest_result(),
    )

    assert dashboard.success
    assert dashboard.top_performing_modules
    assert dashboard.top_performing_modules[0].module in {"Weak Spot Collision", "YPI", "Pitch Mix Matchup"}
    assert dashboard.worst_performing_modules
    assert dashboard.thirty_day_trends.label == "30-Day Trends"
    assert dashboard.season_trends.label == "Season Trends"
    archetypes = {item.archetype: item for item in dashboard.archetype_success_rates}
    assert archetypes["YPI"].wins == 1
    assert archetypes["Catcher Power"].false_positives == 1
    assert any("Top Performing Module" in item for item in dashboard.trend_summaries)


def test_dashboard_exports_dashboard_json():
    dashboard = build_calibration_dashboard(_calibration_result(), postmortem_reports=[_postmortem_report()], backtest_result=_backtest_result())

    with TemporaryDirectory() as temp_dir:
        path = CalibrationDashboardEngine().export_json(dashboard, temp_dir)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

    assert path.name == "dashboard.json"
    assert payload["modules"]
    assert payload["top_performing_modules"]
    assert payload["thirty_day_trends"]["module_trends"]


def test_existing_engines_can_build_dashboards():
    calibration_result = _calibration_result()
    backtest_result = _backtest_result()
    postmortem = _postmortem_report()

    calibration_dashboard = FormulaCalibrationEngine().build_dashboard(
        calibration_result,
        postmortem_reports=[postmortem],
        backtest_result=backtest_result,
    )
    backtest_dashboard = HistoricalBacktestEngine().build_dashboard(
        backtest_result,
        calibration_result=calibration_result,
        postmortem_reports=[postmortem],
    )
    postmortem_engine = PostMortemEngine()
    postmortem_engine.winner_log.extend(postmortem.winner_log)
    postmortem_engine.loser_log.extend(postmortem.loser_log)
    postmortem_engine.false_positive_log.extend(postmortem.false_positive_log)
    postmortem_dashboard = postmortem_engine.build_dashboard(calibration_result=calibration_result, backtest_result=backtest_result)

    assert calibration_dashboard.success
    assert backtest_dashboard.success
    assert postmortem_dashboard.success
