from dataclasses import is_dataclass
import json

from russworks.backtesting import (
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
    DailyBacktestSummary,
    HistoricalBacktestEngine,
)
from russworks.data import DailySlate
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, WatchlistImport
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.postmortem import ActualHomeRunEntry


def _batters(team: str, prefix: str):
    tags_by_slot = {
        1: ["YPI", "Non-superstar core"],
        4: ["Veteran", "Power Threat"],
        8: ["Catcher"],
    }
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=10.0 + slot,
            pitch_mix_score=6.0 + (slot % 3),
            projected_ab=4,
            projected_hits=1.0,
            tags=tags_by_slot.get(slot, ["Non-superstar core"] if slot == 2 else []),
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _slate(day: str) -> DailySlate:
    away = "KC" if day.endswith("13") else "SEA"
    home = "TEX" if day.endswith("13") else "OAK"
    game_id = f"{away.lower()}-{home.lower()}-{day}"
    away_pitcher = PitcherIntake(
        name=f"{away} Starter",
        team=away,
        throws=Handedness.R,
        projected_hr=1.4,
        projected_hits=6.0,
        tags=["weak bullpen", "fastball"],
        confirmed=True,
    )
    home_pitcher = PitcherIntake(
        name=f"{home} Starter",
        team=home,
        throws=Handedness.L,
        projected_hr=1.6,
        projected_hits=6.2,
        tags=["overworked bullpen", "slider"],
        confirmed=True,
    )
    environment = GameEnvironment(
        game_id=game_id,
        date=day,
        away_team=away,
        home_team=home,
        park="Globe Life Field",
        temperature_f=90.0,
        wind_mph=9.0,
        wind_direction="out",
        humidity_pct=55.0,
        roof="open",
        weather_hr_pct=8.0,
        weather_distance_ft=12.0,
        park_hr_factor=8.0,
        umpire=Umpire(name="Russ Zone", zone_type="Hitter", run_lean=1.2),
    )
    away_batters = _batters(away, away)
    home_batters = _batters(home, home)
    game = GameIntake(
        game_id=game_id,
        date=day,
        away_team=TeamIntake(team=away, batters=away_batters, starting_pitcher=away_pitcher),
        home_team=TeamIntake(team=home, batters=home_batters, starting_pitcher=home_pitcher),
        environment=environment,
        umpire=environment.umpire,
        weak_spots=[
            PitcherWeakSpot(pitcher_name=f"{away} Starter", pitch="slider", weakness_score=6.0),
            PitcherWeakSpot(pitcher_name=f"{home} Starter", pitch="fastball", weakness_score=6.0),
        ],
        hr_matchups=[
            HRMatchup(
                batter_name=f"{home} Batter 1",
                pitcher_name=f"{away} Starter",
                pitch="slider",
                matchup_score=8.5,
                exit_velo=106.0,
                angle=27.0,
                distance=408.0,
            ),
            HRMatchup(
                batter_name=f"{away} Batter 4",
                pitcher_name=f"{home} Starter",
                pitch="fastball",
                matchup_score=7.5,
                exit_velo=104.0,
                angle=25.0,
                distance=401.0,
            ),
        ],
    )
    return DailySlate(
        date=day,
        games=[game],
        watchlist=WatchlistImport(games=[game], batters=[home_batters[0], away_batters[3]]),
    )


def _actual_home_runs(day: str):
    slate = _slate(day)
    game = slate.games[0]
    return [
        ActualHomeRunEntry(
            team=game.home_team.team,
            batter=f"{game.home_team.team} Batter 1",
            pitch="slider",
            pitcher=f"{game.away_team.team} Starter",
            inning=2,
            exit_velocity=106.0,
            distance=408.0,
            angle=27.0,
        ),
        ActualHomeRunEntry(
            team=game.away_team.team,
            batter=f"{game.away_team.team} Batter 4",
            pitch="fastball",
            pitcher=f"{game.home_team.team} Starter",
            inning=5,
            exit_velocity=104.0,
            distance=401.0,
            angle=25.0,
        ),
    ]


def _engine() -> HistoricalBacktestEngine:
    return HistoricalBacktestEngine(slate_loader=_slate, actual_hr_loader=_actual_home_runs)


def test_phase17_backtest_models_are_dataclasses():
    assert is_dataclass(BacktestRequest)
    assert is_dataclass(BacktestResult)
    assert is_dataclass(BacktestSummary)
    assert is_dataclass(DailyBacktestSummary)


def test_historical_backtest_runs_daily_pipeline_and_range_summary():
    result = _engine().run(BacktestRequest(start_date="2026-06-13", end_date="2026-06-14"))

    assert result.success
    assert len(result.daily_summaries) == 2
    assert result.summary.dates_tested == 2
    assert result.summary.total_games == 2
    assert result.summary.total_batters_reviewed == 36
    assert result.summary.total_hrs_hit == 4
    assert result.summary.step3_hits == 4
    assert result.summary.step4_hits == 4
    assert result.summary.step5_hits >= 1
    assert result.summary.step3_hit_rate == 1.0
    assert result.summary.step4_hit_rate == 1.0
    assert result.summary.ypi_hits >= 2
    assert result.summary.veteran_hits >= 2
    assert result.summary.weak_spot_hits >= 2
    assert result.summary.pitch_mix_hits >= 2


def test_daily_summary_tracks_requested_archetype_hit_rates():
    result = _engine().run(BacktestRequest(start_date="2026-06-13", end_date="2026-06-13"))
    daily = result.daily_summaries[0]

    assert daily.total_hrs_hit == 2
    assert daily.step3_hit_rate == 1.0
    assert daily.step4_hit_rate == 1.0
    assert daily.non_superstar_hit_rate >= 0.5
    assert daily.ypi_hit_rate >= 0.5
    assert daily.veteran_hit_rate >= 0.5
    assert daily.weak_spot_hit_rate >= 0.5
    assert daily.pitch_mix_hit_rate >= 0.5


def test_backtest_json_export_contains_daily_and_range_summaries():
    engine = _engine()
    result = engine.run(BacktestRequest(start_date="2026-06-13", end_date="2026-06-13"))
    payload = json.loads(engine.export_json(result))

    assert payload["request"]["start_date"] == "2026-06-13"
    assert payload["summary"]["total_hrs_hit"] == 2
    assert payload["daily_summaries"][0]["date"] == "2026-06-13"
    assert "calibration_recommendations" in payload


def test_backtest_rejects_invalid_date_range():
    result = _engine().run(BacktestRequest(start_date="2026-06-14", end_date="2026-06-13"))

    assert not result.success
    assert result.errors
    assert "end_date" in result.errors[0]
