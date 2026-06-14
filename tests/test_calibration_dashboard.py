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
from russworks.calibration import CalibrationMetric, CalibrationRecommendation, CalibrationResult, FormulaCalibrationEngine
from russworks.dashboard import (
    AccuracyBucket,
    AccuracyReview,
    ArchetypePerformance,
    CalibrationDashboard,
    CalibrationDashboardEngine,
    ModulePerformance,
    TrendReport,
    build_calibration_dashboard,
)
from russworks.postmortem import (
    ActualHomeRunEntry,
    AdjustmentLogEntry,
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
    assert is_dataclass(AccuracyBucket)
    assert is_dataclass(AccuracyReview)


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


def test_accuracy_review_summarizes_postmortem_results_by_operating_groups():
    postmortem = PostMortemReport(
        actual_home_runs=[
            ActualHomeRunEntry("KC", "Power Bat", "Fastball", "Starter", 1, 104.0, 410.0, 28.0),
            ActualHomeRunEntry("TEX", "Missed Bat", "Slider", "Starter", 3, 103.0, 405.0, 24.0),
        ],
        winner_log=[
            WinnerLogEntry("KC", "Power Bat", "Fastball", "Starter", 1, 104.0, 410.0, 28.0, slip_names=["KC Core"], slip_types=["core"], archetypes=["Core"], source="step5_hit"),
            WinnerLogEntry("TEX", "Missed Bat", "Slider", "Starter", 3, 103.0, 405.0, 24.0, archetypes=["Missed By Step 5"], source="missed_by_step5"),
        ],
        loser_log=[
            LoserLogEntry("KC", "Over Ranked", "KC Core", "core", "A+", "A+", 94.0, "core", archetypes=["Core"]),
        ],
        false_positive_log=[
            FalsePositiveEntry("KC", "Over Ranked", "KC Core", "core", "High-confidence miss.", ["TAG", "CPS"]),
        ],
    )
    calibration = CalibrationResult(
        metrics=[
            CalibrationMetric("TAG", 10, 4, 0.4, 2, 1, 0.7),
            CalibrationMetric("Umpire", 10, 1, 0.1, 5, 4, 0.2),
        ],
        recommended_adjustments=[CalibrationRecommendation("TAG", "review", 0.0, "medium", "TAG pressure")],
    )
    report_payload = {
        "step3": {
            "batter_reviews": [
                {"batter": "Power Bat", "team": "KC", "score_band": "Elite Core", "tier": "Gold", "russ_score": 91.0, "confidence": {"grade": "High"}},
                {"batter": "Missed Bat", "team": "TEX", "score_band": "Value/Non-Superstar Core", "tier": "Silver", "russ_score": 71.0, "confidence": {"grade": "Medium"}},
                {"batter": "Over Ranked", "team": "KC", "score_band": "Elite Core", "tier": "Gold", "russ_score": 94.0, "confidence": {"grade": "High"}},
            ]
        },
        "step4": {
            "team_rankings": [
                {"team": "KC", "cluster_strength_label": "Nuclear Cluster", "batter_count": 2},
                {"team": "TEX", "cluster_strength_label": "Value Cluster", "batter_count": 1},
            ]
        },
        "step5": {
            "core_slips": [
                {
                    "name": "KC Core",
                    "slip_type": "core",
                    "legs": [
                        {"batter": "Power Bat", "team": "KC"},
                        {"batter": "Over Ranked", "team": "KC"},
                    ],
                }
            ]
        },
    }

    dashboard = CalibrationDashboardEngine().build_dashboard(
        calibration_result=calibration,
        postmortem_reports=[postmortem],
        report_payload=report_payload,
    )

    assert dashboard.accuracy_review is not None
    assert dashboard.accuracy_review.hr_events_acquired == 2
    assert dashboard.accuracy_review.winners == 2
    assert dashboard.accuracy_review.false_positives == 1
    assert {bucket.label for bucket in dashboard.accuracy_review.hit_rate_by_russ_tier} == {"Elite Core", "Value/Non-Superstar Core"}
    assert {bucket.label for bucket in dashboard.accuracy_review.hit_rate_by_confidence_grade} == {"High", "Medium"}
    assert dashboard.accuracy_review.hit_rate_by_slip_type[0].label == "core"
    assert dashboard.accuracy_review.top_false_positives[0]["batter"] == "Over Ranked"
    assert dashboard.accuracy_review.top_false_negatives[0]["batter"] == "Missed Bat"
    assert dashboard.accuracy_review.best_performing_modules[0].module == "TAG"
    assert dashboard.accuracy_review.worst_performing_modules[0].module == "Umpire"
    assert dashboard.accuracy_review.top_calibration_recommendations[0]["module"] == "TAG"


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


def test_postmortem_dashboard_writes_non_zero_operations_summary():
    report = PostMortemReport(
        actual_home_runs=[
            ActualHomeRunEntry("TEX", "Winner One", "Slider", "Pitcher", 1, 101.0, 400.0, 25.0),
            ActualHomeRunEntry("KC", "Winner Two", "Fastball", "Pitcher", 2, 102.0, 410.0, 26.0),
        ],
        winner_log=[WinnerLogEntry("TEX", "Winner One", "Slider", "Pitcher", 1, 101.0, 400.0, 25.0)],
        loser_log=[LoserLogEntry("TEX", "Miss One", "Slip", "core", "A", "A", 90.0, "core")],
        false_positive_log=[FalsePositiveEntry("TEX", "Miss One", "Slip", "core", "Miss", ["TAG"])],
        adjustment_log=[AdjustmentLogEntry("TAG", "down", "Miss pressure", 1, "Review")],
    )
    calibration = CalibrationResult(
        recommended_adjustments=[
            CalibrationRecommendation("TAG", "review", 0.0, "medium", "Review TAG pressure")
        ]
    )
    dashboard = CalibrationDashboardEngine().build_dashboard(
        postmortem_reports=[report],
        calibration_result=calibration,
    )

    with TemporaryDirectory() as temp_dir:
        path = CalibrationDashboardEngine().export_json(dashboard, Path(temp_dir) / "data" / "dashboard")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

    assert payload["operations_summary"]["hr_events_acquired"] == 2
    assert payload["operations_summary"]["winners"] == 1
    assert payload["operations_summary"]["misses"] == 1
    assert payload["operations_summary"]["false_positives"] == 1
    assert payload["operations_summary"]["adjustments"] == 1
    assert payload["operations_summary"]["calibration_recommendations"] == 1


def test_later_daily_dashboard_export_does_not_zero_existing_operations_summary():
    with TemporaryDirectory() as temp_dir:
        dashboard_dir = Path(temp_dir) / "data" / "dashboard"
        dashboard_dir.mkdir(parents=True)
        existing = CalibrationDashboard(
            generated_at="2026-06-14T06:02:00Z",
            operations_summary={
                "last_slate_run": "2026-06-13T10:00:00Z",
                "last_postmortem_run": "2026-06-14T06:02:00Z",
                "last_successful_acquisition": "2026-06-14T06:02:00Z",
                "hr_events_acquired": 45,
                "winners": 45,
                "misses": 24,
                "false_positives": 24,
                "adjustments": 22,
                "calibration_recommendations": 22,
            },
        )
        CalibrationDashboardEngine().export_json(existing, dashboard_dir)

        daily_dashboard = CalibrationDashboardEngine().build_dashboard()
        path = CalibrationDashboardEngine().export_json(daily_dashboard, dashboard_dir)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

    assert payload["operations_summary"]["hr_events_acquired"] == 45
    assert payload["operations_summary"]["winners"] == 45
    assert payload["operations_summary"]["misses"] == 24
    assert payload["operations_summary"]["false_positives"] == 24
    assert payload["operations_summary"]["adjustments"] == 22
    assert payload["operations_summary"]["calibration_recommendations"] == 22


def test_new_postmortem_artifacts_update_operations_summary():
    with TemporaryDirectory() as temp_dir:
        data_root = Path(temp_dir) / "data"
        dashboard_dir = data_root / "dashboard"
        dashboard_dir.mkdir(parents=True)
        CalibrationDashboardEngine().export_json(
            CalibrationDashboard(
                generated_at="2026-06-14T06:02:00Z",
                operations_summary={
                    "hr_events_acquired": 2,
                    "winners": 1,
                    "misses": 1,
                    "false_positives": 1,
                    "adjustments": 1,
                    "calibration_recommendations": 1,
                },
            ),
            dashboard_dir,
        )
        postmortem_dir = data_root / "postmortem" / "2026-06-14"
        postmortem_dir.mkdir(parents=True)
        _write_json(
            postmortem_dir / "run_metadata.json",
            {
                "date": "2026-06-14",
                "executed_at": "2026-06-15T06:02:00Z",
                "actual_home_runs_loaded": 4,
            },
        )
        _write_json(
            postmortem_dir / "postmortem_report.json",
            {
                "actual_home_runs": [{}, {}, {}, {}],
                "winner_log": [{}, {}, {}, {}],
                "loser_log": [{}, {}, {}],
                "false_positive_log": [{}, {}],
                "adjustment_log": [{}, {}],
            },
        )
        _write_json(
            postmortem_dir / "calibration_result.json",
            {"recommended_adjustments": [{}, {}, {}]},
        )

        path = CalibrationDashboardEngine().export_json(CalibrationDashboardEngine().build_dashboard(), dashboard_dir)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

    assert payload["operations_summary"]["last_postmortem_run"] == "2026-06-15T06:02:00Z"
    assert payload["operations_summary"]["last_successful_acquisition"] == "2026-06-15T06:02:00Z"
    assert payload["operations_summary"]["hr_events_acquired"] == 4
    assert payload["operations_summary"]["winners"] == 4
    assert payload["operations_summary"]["misses"] == 3
    assert payload["operations_summary"]["false_positives"] == 2
    assert payload["operations_summary"]["adjustments"] == 2
    assert payload["operations_summary"]["calibration_recommendations"] == 3


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
