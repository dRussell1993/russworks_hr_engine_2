from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.data import DailySlate
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, WatchlistImport
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.pipeline import DailyRunRequest, DailyRunResult, RussWorksPipeline, run_daily_pipeline
from russworks.run import main as run_cli


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
            hr_pct=9.0 + slot,
            pitch_mix_score=6.0 + (slot % 3),
            projected_ab=4,
            projected_hits=1.0,
            tags=tags_by_slot.get(slot, []),
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _slate(date: str = "2026-06-13", *, missing_weak_spots: bool = False) -> DailySlate:
    away = "KC"
    home = "TEX"
    away_pitcher = PitcherIntake(
        name="KC Starter",
        team=away,
        throws=Handedness.R,
        projected_hr=1.4,
        projected_hits=6.0,
        tags=["weak bullpen", "slider"],
        confirmed=True,
    )
    home_pitcher = PitcherIntake(
        name="TEX Starter",
        team=home,
        throws=Handedness.L,
        projected_hr=1.6,
        projected_hits=6.2,
        tags=["overworked bullpen", "fastball"],
        confirmed=True,
    )
    environment = GameEnvironment(
        game_id="tex-kc-1",
        date=date,
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
        game_id="tex-kc-1",
        date=date,
        away_team=TeamIntake(team=away, batters=away_batters, starting_pitcher=away_pitcher),
        home_team=TeamIntake(team=home, batters=home_batters, starting_pitcher=home_pitcher),
        environment=environment,
        umpire=environment.umpire,
        weak_spots=[]
        if missing_weak_spots
        else [
            PitcherWeakSpot(pitcher_name="KC Starter", pitch="slider", weakness_score=6.0),
            PitcherWeakSpot(pitcher_name="TEX Starter", pitch="fastball", weakness_score=6.0),
        ],
        hr_matchups=[
            HRMatchup(
                batter_name="TEX Batter 1",
                pitcher_name="KC Starter",
                pitch="slider",
                matchup_score=8.5,
                exit_velo=106.0,
                angle=27.0,
                distance=408.0,
            ),
            HRMatchup(
                batter_name="KC Batter 4",
                pitcher_name="TEX Starter",
                pitch="fastball",
                matchup_score=7.5,
                exit_velo=104.0,
                angle=25.0,
                distance=401.0,
            ),
        ],
    )
    return DailySlate(
        date=date,
        games=[game],
        watchlist=WatchlistImport(games=[game], batters=[home_batters[0], away_batters[3]]),
    )


def _write_csv(root: Path, name: str, header: list[str], rows: list[list[object]]) -> None:
    path = root / f"{name}.csv"
    path.write_text(
        "\n".join([",".join(header), *[",".join(str(value) for value in row) for row in rows]]),
        encoding="utf-8",
    )


def _write_daily_csv_fixture(root: Path, date: str) -> None:
    day = root / date
    day.mkdir(parents=True)
    _write_csv(day, "watchlist", ["name", "team", "lineup_slot", "bats", "hr_pct"], [["TEX Watch", "TEX", 1, "R", 12]])
    lineup_rows = []
    for team in ["KC", "TEX"]:
        for slot in range(1, 10):
            lineup_rows.append([date, "tex-kc-1", f"{team} Batter {slot}", team, slot, "R", 10 + slot])
    _write_csv(day, "lineups", ["date", "game_id", "name", "team", "lineup_slot", "bats", "hr_pct"], lineup_rows)
    _write_csv(
        day,
        "pitchers",
        ["game_id", "name", "team", "throws", "projected_hr", "confirmed"],
        [["tex-kc-1", "KC Starter", "KC", "R", 1.4, "true"], ["tex-kc-1", "TEX Starter", "TEX", "L", 1.6, "true"]],
    )
    _write_csv(
        day,
        "weather",
        ["game_id", "date", "away_team", "home_team", "park", "temperature_f", "wind_mph", "wind_direction", "weather_hr_pct", "weather_distance_ft", "park_hr_factor"],
        [["tex-kc-1", date, "KC", "TEX", "Globe Life Field", 90, 9, "out", 8, 12, 8]],
    )
    _write_csv(day, "umpires", ["game_id", "name", "zone_type", "run_lean"], [["tex-kc-1", "Russ Zone", "Hitter", 1.2]])
    _write_csv(day, "weak_spots", ["game_id", "pitcher_name", "pitch", "weakness_score"], [["tex-kc-1", "KC Starter", "slider", 6], ["tex-kc-1", "TEX Starter", "fastball", 6]])
    _write_csv(day, "hr_matchups", ["game_id", "batter_name", "pitcher_name", "pitch", "matchup_score"], [["tex-kc-1", "TEX Batter 1", "KC Starter", "slider", 8]])


def test_phase19_daily_models_are_dataclasses():
    assert is_dataclass(DailyRunRequest)
    assert is_dataclass(DailyRunResult)


def test_daily_pipeline_runs_all_steps_and_saves_report_json():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date="2026-06-13", output_root=str(output_root))
        pipeline = RussWorksPipeline(slate_loader=lambda date, request: _slate(date))

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert result.success
        assert result.validation_status == "valid"
        assert result.total_batters_reviewed == 18
        assert result.step3_result.reviewed_batters == 18
        assert result.step3_result.skipped_batters == []
        assert result.step4_result.success
        assert result.step5_result.success
        assert result.full_report.context.report_date == "2026-06-13"
        assert result.full_report.context.games_reviewed == 1
        assert result.full_report.step3.total_batters_reviewed == 18

        report_path = Path(result.report_json_path)
        assert report_path == output_root / "2026-06-13" / "russworks_full_report.json"
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["context"]["validation_status"] == "valid"
        assert payload["context"]["game_ids"] == ["tex-kc-1"]


def test_daily_pipeline_blocks_when_step2_validation_is_incomplete():
    with TemporaryDirectory() as temp_dir:
        request = DailyRunRequest(date="2026-06-13", output_root=str(Path(temp_dir) / "outputs"))
        pipeline = RussWorksPipeline(slate_loader=lambda date, request: _slate(date, missing_weak_spots=True))

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert not result.success
        assert result.validation_status == "invalid"
        assert "weak_spot" in result.missing_data
        assert "Step 2 validation incomplete" in result.errors[0]
        assert result.step3_result is None
        assert result.report_json_path == ""


def test_top_level_run_daily_pipeline_uses_csv_data_connectors():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        _write_daily_csv_fixture(data_root, "2026-06-13")

        result = run_daily_pipeline("2026-06-13", data_root=str(data_root), output_root=str(output_root))

        assert result.success
        assert Path(result.report_json_path).exists()
        assert result.total_batters_reviewed == 18


def test_cli_runs_pipeline_and_returns_success_code():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        _write_daily_csv_fixture(data_root, "2026-06-13")

        exit_code = run_cli(["--date", "2026-06-13", "--data-root", str(data_root), "--output-root", str(output_root)])

        assert exit_code == 0
        assert (output_root / "2026-06-13" / "russworks_full_report.json").exists()
