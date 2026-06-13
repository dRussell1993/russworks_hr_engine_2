from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.data import DailySlate
from russworks.integrity import (
    DataIntegrityResult,
    IntegrityAlert,
    IntegrityEngine,
    IntegrityReport,
    IntegritySeverity,
    ProviderIntegrityResult,
)
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, WatchlistImport
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.providers import DailySlateProvider, InMemoryDataProvider, ProviderResult


DATE = "2026-06-13"


def _batters(team: str):
    return [
        BatterIntake(
            name=f"{team} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=10.0,
            pitch_mix_score=5.0,
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _slate() -> DailySlate:
    umpire = Umpire("Integrity Zone", called_strike_rate=0.48, accuracy=0.95, consistency=0.93, run_lean=1.0)
    game = GameIntake(
        game_id="tex-kc-1",
        date=DATE,
        away_team=TeamIntake("KC", _batters("KC"), PitcherIntake("KC Starter", "KC", throws=Handedness.R, projected_hr=1.4, confirmed=True)),
        home_team=TeamIntake("TEX", _batters("TEX"), PitcherIntake("TEX Starter", "TEX", throws=Handedness.L, projected_hr=1.6, confirmed=True)),
        environment=GameEnvironment(
            game_id="tex-kc-1",
            date=DATE,
            away_team="KC",
            home_team="TEX",
            park="Globe Life Field",
            temperature_f=90.0,
            wind_mph=9.0,
            humidity_pct=55.0,
            roof="open",
            weather_hr_pct=8.0,
            weather_distance_ft=12.0,
            park_hr_factor=8.0,
            umpire=umpire,
        ),
        umpire=umpire,
        weak_spots=[PitcherWeakSpot("KC Starter", "slider", weakness_score=6.0)],
        hr_matchups=[HRMatchup("TEX Batter 1", "KC Starter", "slider", matchup_score=7.0, exit_velo=105.0, angle=25.0, distance=405.0)],
    )
    return DailySlate(date=DATE, games=[game], watchlist=WatchlistImport(games=[game]))


def test_phase30_integrity_models_are_dataclasses():
    assert is_dataclass(IntegrityAlert)
    assert is_dataclass(DataIntegrityResult)
    assert is_dataclass(ProviderIntegrityResult)
    assert is_dataclass(IntegrityReport)


def test_integrity_engine_accepts_clean_daily_slate_and_exports_json():
    report = IntegrityEngine().validate_daily_slate(_slate())

    assert report.success
    assert report.date == DATE
    assert report.severity_counts["ERROR"] == 0
    assert report.severity_counts["CRITICAL"] == 0

    with TemporaryDirectory() as temp_dir:
        output_path = IntegrityEngine().export_json(report, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "integrity_report.json"
    assert payload["success"]
    assert payload["severity_counts"]["ERROR"] == 0


def test_integrity_engine_flags_duplicates_ranges_handedness_and_team_mismatches():
    slate = _slate()
    game = slate.games[0]
    bad_batter = game.home_team.batters[0]
    game.home_team.batters[1] = BatterIntake(
        name=bad_batter.name,
        team="KC",
        lineup_slot=bad_batter.lineup_slot,
        bats="X",
        hr_pct=125.0,
        confirmed=True,
    )
    game.environment.temperature_f = 150.0
    game.environment.park_hr_factor = -1.0
    game.umpire.run_lean = 9.0

    report = IntegrityEngine().validate_daily_slate(slate)
    categories = {alert.category for alert in report.alerts}

    assert not report.success
    assert IntegritySeverity.ERROR.value in report.severity_counts
    assert "duplicate_player" in categories
    assert "duplicate_lineup_slot" in categories
    assert "invalid_handedness" in categories
    assert "out_of_range" in categories
    assert "team_opponent_mismatch" in categories


def test_integrity_engine_validates_provider_results_and_daily_slate_provider_helper():
    slate = _slate()
    provider_result = ProviderResult(provider="mlb_stats", dataset="lineups", success=False, errors=["timeout"])
    report = IntegrityEngine().validate_daily_slate(slate, provider_results=[provider_result])

    assert not report.success
    assert report.provider_results[0].provider == "mlb_stats"
    assert report.provider_results[0].alerts[0].category == "provider_failure"

    slate_provider = DailySlateProvider(providers=[], fallback_provider=InMemoryDataProvider({}))
    slate_provider.results.append(provider_result)
    slate_provider.health_statuses = []
    helper_report = slate_provider.integrity_report(slate)

    assert helper_report.provider_results[0].dataset == "lineups"


def test_pipeline_exports_integrity_report_and_command_center_surfaces_alert_counts():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate()).run_daily_pipeline(DATE, request)

        assert result.success
        assert result.integrity_report is not None
        assert result.integrity_report_path == str(output_root.parent / "integrity" / "integrity_report.json")
        assert Path(result.integrity_report_path).exists()

        command_center = CommandCenterEngine().build_report(daily_run_result=result)

        assert command_center.slate_status.integrity_alerts["ERROR"] == 0
        assert command_center.execution_summary.integrity_report_path == result.integrity_report_path
        assert result.integrity_report_path in command_center.execution_summary.exports_generated


def test_dashboard_accepts_integrity_report_summaries():
    report = IntegrityEngine().validate_daily_slate(_slate())
    dashboard = CalibrationDashboardEngine().build_dashboard(integrity_report=report)

    assert dashboard.integrity_summaries == ["Data integrity monitor found no alerts."]
