from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import (
    CommandCenterEngine,
    CommandCenterReport,
    DailyExecutionSummary,
    DailySlateStatus,
    FormulaHealthReport,
    build_command_center_report,
)
from russworks.dashboard import AccuracyReview, CalibrationDashboard, ModulePerformance
from russworks.data import DailySlate
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.optimizer import OptimizationResult, OptimizationScenario
from russworks.pipeline import DailyRunRequest, DailyRunResult
from russworks.providers import ProviderHealth
from russworks.recommendations import ModuleRecommendation, RecommendationReport
from russworks.trends import TrendMetric, TrendSummary


DATE = "2026-06-13"


def _batters(team: str):
    return [
        BatterIntake(
            name=f"{team} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R,
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _slate() -> DailySlate:
    umpire = Umpire("Command Zone")
    game = GameIntake(
        game_id="tex-kc-1",
        date=DATE,
        away_team=TeamIntake("KC", _batters("KC"), PitcherIntake("KC Starter", "KC", confirmed=True)),
        home_team=TeamIntake("TEX", _batters("TEX"), PitcherIntake("TEX Starter", "TEX", confirmed=True)),
        environment=GameEnvironment(
            game_id="tex-kc-1",
            date=DATE,
            away_team="KC",
            home_team="TEX",
            park="Globe Life Field",
            umpire=umpire,
        ),
        umpire=umpire,
        weak_spots=[PitcherWeakSpot("KC Starter", "slider", weakness_score=6.0)],
        hr_matchups=[HRMatchup("TEX Batter 1", "KC Starter", "slider", matchup_score=7.0)],
    )
    return DailySlate(
        date=DATE,
        games=[game],
        metadata={"provider_statuses": "mlb_stats:ok,weather:ok"},
    )


def _daily_run_result(slate: DailySlate) -> DailyRunResult:
    return DailyRunResult(
        request=DailyRunRequest(date=DATE),
        success=True,
        validation_status="valid",
        total_batters_reviewed=18,
        output_dir=f"data/outputs/{DATE}",
        report_json_path=f"data/outputs/{DATE}/russworks_full_report.json",
        slate=slate,
    )


def _dashboard() -> CalibrationDashboard:
    tag = ModulePerformance("TAG", appearances=40, wins=12, losses=28, hit_rate=0.30, false_positives=4, false_negatives=3, confidence_accuracy=0.70)
    umpire = ModulePerformance("Umpire", appearances=30, wins=2, losses=28, hit_rate=0.0667, false_positives=12, false_negatives=6, confidence_accuracy=0.20)
    return CalibrationDashboard(
        generated_at="2026-06-13T00:00:00Z",
        modules=[tag, umpire],
        top_performing_modules=[tag],
        worst_performing_modules=[umpire],
        accuracy_review=AccuracyReview(hr_events_acquired=4, winners=2, misses=2, false_positives=1, hit_rate=0.5),
    )


def _recommendations() -> RecommendationReport:
    return RecommendationReport(
        generated_at="2026-06-13T00:00:00Z",
        modules=[
            ModuleRecommendation(
                module="TAG",
                current_weight=45.0,
                suggested_weight=47.5,
                confidence="medium",
                trend_direction="increase",
                reasoning="TAG is outperforming.",
            )
        ],
    )


def _trends() -> TrendSummary:
    return TrendSummary(
        generated_at="2026-06-13T00:00:00Z",
        metrics=[
            TrendMetric("TAG", 0.35, 0.32, 0.30, 0.28, "Heating Up", 40),
            TrendMetric("Umpire", 0.02, 0.04, 0.06, 0.08, "Cooling Off", 30),
        ],
        heating_up=["TAG"],
        cooling_off=["Umpire"],
    )


def _optimizer() -> OptimizationResult:
    return OptimizationResult(
        generated_at="2026-06-13T00:00:00Z",
        scenarios=[
            OptimizationScenario(
                module="TAG",
                current_weight=45.0,
                simulated_weight=49.5,
                simulated_change_pct=0.10,
                historical_performance=0.30,
                expected_impact=0.05,
                confidence_level="medium",
                recommendation="increase",
                rejected=False,
                reasoning="Simulated increase only.",
            )
        ],
    )


def test_phase27_command_center_models_are_dataclasses():
    assert is_dataclass(DailySlateStatus)
    assert is_dataclass(FormulaHealthReport)
    assert is_dataclass(DailyExecutionSummary)
    assert is_dataclass(CommandCenterReport)


def test_command_center_generates_daily_operator_summary():
    slate = _slate()
    report = CommandCenterEngine().build_report(
        daily_run_result=_daily_run_result(slate),
        dashboard=_dashboard(),
        recommendations=_recommendations(),
        trends=_trends(),
        optimizer=_optimizer(),
        provider_health=[ProviderHealth("mlb_stats", "ok", "2026-06-13T00:00:00Z")],
    )

    assert report.success
    assert report.slate_status.date == DATE
    assert report.slate_status.games_loaded == 1
    assert report.slate_status.batters_loaded == 18
    assert report.slate_status.confirmed_lineups == 2
    assert report.slate_status.missing_lineups == []
    assert report.slate_status.provider_health[0]["provider"] == "mlb_stats"

    assert "TAG" in report.formula_health.top_performing_modules
    assert "Umpire" in report.formula_health.worst_performing_modules
    assert report.formula_health.modules_heating_up == ["TAG"]
    assert report.formula_health.modules_cooling_off == ["Umpire"]
    assert report.formula_health.optimizer_recommendations[0]["module"] == "TAG"
    assert report.formula_health.accuracy_review["hr_events_acquired"] == 4
    assert report.formula_health.accuracy_review["hit_rate"] == 0.5

    assert report.execution_summary.step2_status == "valid"
    assert report.execution_summary.step3_status == "not_run"
    assert report.execution_summary.reports_generated == [f"data/outputs/{DATE}/russworks_full_report.json"]
    assert "data/trends/trends.json" in report.execution_summary.exports_generated
    assert "data/optimizer/optimizer_report.json" in report.execution_summary.exports_generated


def test_command_center_reports_validation_failures_for_incomplete_lineups():
    slate = _slate()
    bad_game = slate.games[0]
    bad_game.home_team.batters.pop()
    report = build_command_center_report(date=DATE, slate=slate)

    assert not report.success
    assert "TEX lineup slot 9" in report.slate_status.validation_failures["missing_lineup_slot"]
    assert "TEX lineup slot 9" in report.slate_status.missing_lineups


def test_command_center_exports_json():
    report = CommandCenterEngine().build_report(
        daily_run_result=_daily_run_result(_slate()),
        dashboard=_dashboard(),
        recommendations=_recommendations(),
        trends=_trends(),
        optimizer=_optimizer(),
    )

    with TemporaryDirectory() as temp_dir:
        output_path = CommandCenterEngine().export_json(report, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "command_center.json"
    assert payload["slate_status"]["games_loaded"] == 1
    assert payload["formula_health"]["modules_heating_up"] == ["TAG"]
