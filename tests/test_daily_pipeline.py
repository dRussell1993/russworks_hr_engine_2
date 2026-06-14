from dataclasses import is_dataclass, replace
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


def _game(game_id: str, date: str, *, complete: bool = True, park_hr_factor: float = 7.5) -> GameIntake:
    away = f"A{game_id}"
    home = f"H{game_id}"
    away_pitcher = PitcherIntake(name=f"{away} Starter", team=away, throws=Handedness.R, projected_hr=1.2, projected_hits=5.0, confirmed=True)
    home_pitcher = PitcherIntake(name=f"{home} Starter", team=home, throws=Handedness.L, projected_hr=1.4, projected_hits=5.5, confirmed=True)
    environment = GameEnvironment(
        game_id=game_id,
        date=date,
        away_team=away,
        home_team=home,
        park=f"{game_id} Park",
        temperature_f=82.0,
        wind_mph=7.0,
        wind_direction="out",
        humidity_pct=50.0,
        roof="open",
        weather_hr_pct=6.0,
        weather_distance_ft=8.0,
        park_hr_factor=park_hr_factor,
        umpire=Umpire(name=f"{game_id} Ump", zone_type="Neutral", run_lean=0.2),
    )
    weak_spots = [] if not complete else [
        PitcherWeakSpot(pitcher_name=away_pitcher.name, pitch="slider", weakness_score=6.0),
        PitcherWeakSpot(pitcher_name=home_pitcher.name, pitch="fastball", weakness_score=6.0),
    ]
    hr_matchups = [] if not complete else [
        HRMatchup(batter_name=f"{home} Batter 1", pitcher_name=away_pitcher.name, pitch="slider", matchup_score=8.0),
        HRMatchup(batter_name=f"{away} Batter 4", pitcher_name=home_pitcher.name, pitch="fastball", matchup_score=7.5),
    ]
    strength_offset = sum(int(char) for char in game_id if char.isdigit()) % 5
    away_batters = _varied_batters(_batters(away, away), strength_offset)
    home_batters = _varied_batters(_batters(home, home), strength_offset + 1)
    return GameIntake(
        game_id=game_id,
        date=date,
        away_team=TeamIntake(team=away, batters=away_batters, starting_pitcher=away_pitcher),
        home_team=TeamIntake(team=home, batters=home_batters, starting_pitcher=home_pitcher),
        environment=environment,
        umpire=environment.umpire,
        weak_spots=weak_spots,
        hr_matchups=hr_matchups,
    )


def _varied_batters(batters, offset: int):
    return [
        replace(
            batter,
            hr_pct=max(1.0, batter.hr_pct + offset - (batter.lineup_slot or 0) * 0.2),
            pitch_mix_score=max(1.0, batter.pitch_mix_score + offset * 0.4),
            projected_hits=max(0.1, batter.projected_hits + offset * 0.1),
        )
        for batter in batters
    ]


def _multi_game_slate(date: str, *, complete_count: int, skipped_count: int) -> DailySlate:
    games = [_game(f"g{i}-h{i}-1", date, complete=True) for i in range(complete_count)]
    games.extend(_game(f"skip{i}-bad{i}-1", date, complete=False) for i in range(skipped_count))
    watchlist = [game.home_team.batters[0] for game in games if game.home_team.batters]
    return DailySlate(date=date, games=games, watchlist=WatchlistImport(games=games, batters=watchlist))


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


def _write_daily_csv_fixture_with_unmatched_matchup(root: Path, date: str) -> None:
    _write_daily_csv_fixture(root, date)
    day = root / date
    _write_csv(day, "weak_spots", ["game_id", "pitcher_name", "pitch", "weakness_score"], [["SEA@OAK", "KC Starter", "slider", 6]])
    _write_csv(day, "hr_matchups", ["game_id", "batter_name", "pitcher_name", "pitch", "matchup_score"], [["SEA@OAK", "TEX Batter 1", "KC Starter", "slider", 8]])


def _write_daily_csv_fixture_without_park_factor(root: Path, date: str) -> None:
    _write_daily_csv_fixture(root, date)
    day = root / date
    _write_csv(
        day,
        "weather",
        ["game_id", "date", "away_team", "home_team", "park", "temperature_f", "wind_mph", "wind_direction", "weather_hr_pct", "weather_distance_ft"],
        [["tex-kc-1", date, "KC", "TEX", "Globe Life Field", 90, 9, "out", 8, 12]],
    )


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
        assert Path(result.operator_report_path) == output_root / "2026-06-13" / "russworks_operator_report.md"
        assert Path(result.operator_report_path).exists()
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["context"]["validation_status"] == "valid"
        assert payload["context"]["game_ids"] == ["tex-kc-1"]
        assert payload["explanations"]["batter_explanations"]
        assert (output_root.parent / "explanations" / "explanations.json").exists()
        assert Path(result.dashboard_path) == output_root.parent / "dashboard" / "dashboard.json"
        assert Path(result.command_center_path) == output_root.parent / "command_center" / "command_center.json"
        assert Path(result.web_dashboard_path) == output_root.parent / "web" / "dashboard_data.json"
        assert Path(result.dashboard_path).exists()
        assert Path(result.command_center_path).exists()
        assert Path(result.web_dashboard_path).exists()


def test_phase43_score_spread_cluster_spread_and_operator_markdown_report():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date="2026-06-13", output_root=str(output_root))
        pipeline = RussWorksPipeline(slate_loader=lambda date, request: _multi_game_slate(date, complete_count=3, skipped_count=0))

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert result.success
        scores = [review.final_russ_score for review in result.step3_result.reviews]
        assert max(scores) < 99.0
        assert len({score for score in scores}) > 5
        assert any(review.score_band in {"Elite Core", "Core Target", "Strong Play", "Value/Non-Superstar Core", "Chaos", "Fade"} for review in result.step3_result.reviews)

        cluster_scores = [team.total_cluster_score for team in result.step4_result.ranked_teams]
        assert max(cluster_scores) < 100.0
        assert len({score for score in cluster_scores}) > 1
        assert all(team.cluster_strength_label in {"Nuclear Cluster", "Strong Cluster", "Value Cluster", "Thin Cluster", "Fade Cluster"} for team in result.step4_result.ranked_teams)

        operator_path = Path(result.operator_report_path)
        assert operator_path.exists()
        text = operator_path.read_text(encoding="utf-8")
        assert "STEP 3 — BATTER REVIEW" in text
        assert "STEP 4 — TEAM CLUSTER RANKINGS" in text
        assert "STEP 5 — SLIP CONSTRUCTION" in text
        assert "Production Readiness / Match Integrity" in text
        assert "Confidence warning" in text


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
        assert Path(result.command_center_path).exists()


def test_daily_pipeline_processes_complete_games_when_one_game_is_skipped():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date="2026-06-13", output_root=str(output_root))
        pipeline = RussWorksPipeline(slate_loader=lambda date, request: _multi_game_slate(date, complete_count=14, skipped_count=1))

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert result.success
        assert result.validation_status == "partial"
        assert result.validation_summary["total_games"] == 15
        assert result.validation_summary["complete_games"] == 14
        assert result.validation_summary["skipped_games"] == 1
        assert len(result.complete_games) == 14
        assert len(result.skipped_games) == 1
        assert "hr_matchup" in result.skipped_games[0].missing_data
        assert result.total_batters_reviewed == 14 * 18
        assert result.full_report.context.validation_status == "partial"
        assert result.full_report.context.skipped_games
        assert result.full_report.context.warnings
        dashboard_payload = json.loads(Path(result.dashboard_path).read_text(encoding="utf-8"))
        assert dashboard_payload["validation_summaries"]
        assert dashboard_payload["skipped_game_summaries"]
        command_payload = json.loads(Path(result.command_center_path).read_text(encoding="utf-8"))
        assert command_payload["slate_status"]["skipped_games"]
        assert command_payload["warnings"]


def test_daily_pipeline_fails_when_no_complete_games_remain():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date="2026-06-13", output_root=str(output_root))
        pipeline = RussWorksPipeline(slate_loader=lambda date, request: _multi_game_slate(date, complete_count=0, skipped_count=2))

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert not result.success
        assert result.validation_status == "invalid"
        assert result.validation_summary["complete_games"] == 0
        assert result.validation_summary["skipped_games"] == 2
        assert len(result.skipped_games) == 2
        assert result.step3_result is None
        assert result.report_json_path == ""
        assert Path(result.command_center_path).exists()


def test_missing_park_factor_uses_neutral_fallback_without_skipping_game():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date="2026-06-13", output_root=str(output_root))
        fallback_game = _game("g1-h1-1", "2026-06-13", complete=True, park_hr_factor=0.0)
        pipeline = RussWorksPipeline(
            slate_loader=lambda date, request: DailySlate(
                date=date,
                games=[fallback_game],
                watchlist=WatchlistImport(games=[fallback_game], batters=[fallback_game.home_team.batters[0]]),
            )
        )

        result = pipeline.run_daily_pipeline("2026-06-13", request)

        assert result.success
        assert result.validation_status == "valid"
        assert result.validation_summary["complete_games"] == 1
        assert result.validation_summary["skipped_games"] == 0
        assert result.validation_summary["park_factor_fallback_games"] == 1
        assert result.validation_summary["park_factor_fallback_game_ids"] == ["g1-h1-1"]
        assert result.skipped_games == []
        assert "g1-h1-1: Neutral park factor fallback used" in result.warnings
        assert all(review.park_factor_grade == "Neutral" for review in result.step3_result.reviews)
        assert all(review.park_factor_confidence < 0.8 for review in result.step3_result.reviews)
        assert all(any("Neutral park factor fallback used" in reason for reason in review.confidence_reasoning) for review in result.step3_result.reviews)
        assert all(review.confidence_breakdown["environment_certainty"] <= 65.0 for review in result.step3_result.reviews)
        assert all(team.confidence_breakdown["environment_certainty"] <= 65.0 for team in result.step4_result.ranked_teams)
        assert "Neutral park factor fallback used" in result.full_report.context.warnings[0]

        dashboard_payload = json.loads(Path(result.dashboard_path).read_text(encoding="utf-8"))
        assert "park_factor_fallback_games=1" in dashboard_payload["validation_summaries"][0]
        command_payload = json.loads(Path(result.command_center_path).read_text(encoding="utf-8"))
        assert "g1-h1-1: Neutral park factor fallback used" in command_payload["warnings"]
        assert command_payload["slate_status"]["validation_summary"]["park_factor_fallback_games"] == 1


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
        assert Path(result.dashboard_path).exists()
        assert Path(result.command_center_path).exists()
        assert Path(result.web_dashboard_path).exists()


def test_csv_daily_pipeline_uses_neutral_park_factor_fallback_when_missing():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        _write_daily_csv_fixture_without_park_factor(data_root, "2026-06-13")

        result = run_daily_pipeline("2026-06-13", data_root=str(data_root), output_root=str(output_root))

        assert result.success
        assert result.validation_status == "valid"
        assert result.validation_summary["complete_games"] == 1
        assert result.validation_summary["skipped_games"] == 0
        assert result.validation_summary["park_factor_fallback_games"] == 1
        assert "tex-kc-1: Neutral park factor fallback used" in result.warnings
        assert Path(result.report_json_path).exists()


def test_daily_pipeline_validation_output_includes_unmatched_game_ids():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        _write_daily_csv_fixture_with_unmatched_matchup(data_root, "2026-06-13")

        result = run_daily_pipeline("2026-06-13", data_root=str(data_root), output_root=str(output_root))

        assert not result.success
        assert result.validation_status == "invalid"
        assert result.missing_data["weak_spot"] == ["pitcher weak spot data"]
        assert result.missing_data["hr_matchup"] == ["HR matchup data"]
        assert "weak_spots: SEA@OAK" in result.missing_data["unmatched_game_id"]
        assert "hr_matchups: SEA@OAK" in result.missing_data["unmatched_game_id"]
        assert "unmatched_game_id" in result.errors[0]


def test_cli_runs_pipeline_and_returns_success_code():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        _write_daily_csv_fixture(data_root, "2026-06-13")

        exit_code = run_cli(["--date", "2026-06-13", "--data-root", str(data_root), "--output-root", str(output_root)])

        assert exit_code == 0
        assert (output_root / "2026-06-13" / "russworks_full_report.json").exists()
        assert (output_root.parent / "dashboard" / "dashboard.json").exists()
        assert (output_root.parent / "command_center" / "command_center.json").exists()
        assert (output_root.parent / "web" / "dashboard_data.json").exists()
