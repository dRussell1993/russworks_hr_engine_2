from dataclasses import is_dataclass
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.data import (
    CSVDataProvider,
    DailySlate,
    DataProvider,
    EnvironmentProvider,
    JSONDataProvider,
    LineupProvider,
    MLBDataConnector,
    PitcherProvider,
    WatchlistProvider,
    load_daily_slate,
    load_game_data,
    load_watchlist,
    normalize_game_id,
)
from russworks.intake import validate_step2_intake
from russworks.models import Handedness


def _write_csv(root: Path, dataset: str, rows: list[dict[str, object]]) -> None:
    path = root / f"{dataset}.csv"
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _csv_slate(root: Path) -> None:
    _write_csv(
        root,
        "watchlist",
        [
            {
                "game_id": "tex-kc-1",
                "name": "TEX Watch Bat",
                "team": "TEX",
                "lineup_slot": 3,
                "bats": "R",
                "hr_pct": 14.5,
                "pitch_mix_score": 7.0,
                "tags": "YPI,Non-superstar core",
            }
        ],
    )
    _write_csv(root, "lineups", _lineup_rows("tex-kc-1", "KC", "L") + _lineup_rows("tex-kc-1", "TEX", "R"))
    _write_csv(
        root,
        "pitchers",
        [
            {"game_id": "tex-kc-1", "name": "KC Starter", "team": "KC", "throws": "R", "projected_hr": 1.4, "confirmed": "true"},
            {"game_id": "tex-kc-1", "name": "TEX Starter", "team": "TEX", "throws": "L", "projected_hr": 1.2, "confirmed": "true"},
        ],
    )
    _write_csv(
        root,
        "weather",
        [
            {
                "game_id": "tex-kc-1",
                "date": "2026-06-13",
                "away_team": "KC",
                "home_team": "TEX",
                "park": "Globe Life Field",
                "temperature_f": 91,
                "wind_mph": 8,
                "wind_direction": "out",
                "humidity_pct": 55,
                "roof": "open",
                "weather_hr_pct": 7.5,
                "weather_distance_ft": 10,
            }
        ],
    )
    _write_csv(
        root,
        "umpires",
        [
            {
                "game_id": "tex-kc-1",
                "name": "Russ Zone",
                "zone_type": "Hitter",
                "called_strike_rate": 0.47,
                "accuracy": 0.92,
                "consistency": 0.91,
                "run_lean": 1.1,
            }
        ],
    )
    _write_csv(root, "park_factors", [{"game_id": "tex-kc-1", "park_hr_factor": 8.5}])
    _write_csv(root, "weak_spots", [{"game_id": "tex-kc-1", "pitcher_name": "KC Starter", "pitch": "slider", "weakness_score": 6.5}])
    _write_csv(
        root,
        "hr_matchups",
        [
            {
                "game_id": "tex-kc-1",
                "batter_name": "TEX Batter 1",
                "pitcher_name": "KC Starter",
                "pitch": "slider",
                "matchup_score": 8.0,
                "exit_velo": 106,
                "angle": 27,
                "distance": 405,
            }
        ],
    )


def _json_slate(path: Path) -> None:
    payload = {
        "watchlist": [
            {
                "name": "SEA Watch Bat",
                "team": "SEA",
                "lineup_slot": 2,
                "bats": "L",
                "hr_pct": 11.0,
                "tags": ["Catcher", "YPI"],
            }
        ],
        "lineups": _lineup_rows("sea-oak-1", "SEA", "L") + _lineup_rows("sea-oak-1", "OAK", "R"),
        "pitchers": [
            {"game_id": "sea-oak-1", "name": "SEA Starter", "team": "SEA", "throws": "R", "confirmed": True},
            {"game_id": "sea-oak-1", "name": "OAK Starter", "team": "OAK", "throws": "L", "confirmed": True},
        ],
        "weather": [
            {
                "game_id": "sea-oak-1",
                "date": "2026-06-13",
                "away_team": "SEA",
                "home_team": "OAK",
                "park": "Oakland Coliseum",
                "temperature": 72,
                "wind_speed": 5,
                "wind_direction": "out",
                "humidity": 60,
                "roof_status": "open",
                "hr_park_factor": 5.5,
            }
        ],
        "umpires": [{"game_id": "sea-oak-1", "umpire": "Neutral Zone", "zone_type": "Neutral"}],
        "park_factors": [{"game_id": "sea-oak-1", "hr_park_factor": 5.8}],
        "weak_spots": [{"game_id": "sea-oak-1", "pitcher": "OAK Starter", "pitch_type": "fastball", "score": 5.0}],
        "hr_matchups": [{"game_id": "sea-oak-1", "batter": "SEA Batter 1", "pitcher": "OAK Starter", "pitch_type": "fastball", "score": 7.0}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _lineup_rows(game_id: str, team: str, bats: str) -> list[dict[str, object]]:
    return [
        {
            "game_id": game_id,
            "name": f"{team} Batter {slot}",
            "team": team,
            "lineup_slot": slot,
            "bats": bats,
            "hr_pct": 8.0 + slot,
        }
        for slot in range(1, 10)
    ]


def test_phase16_provider_models_and_interfaces_exist():
    assert issubclass(CSVDataProvider, DataProvider)
    assert issubclass(JSONDataProvider, DataProvider)
    assert is_dataclass(DailySlate)

    assert WatchlistProvider
    assert LineupProvider
    assert PitcherProvider
    assert EnvironmentProvider


def test_normalize_game_id_supports_common_daily_formats():
    assert normalize_game_id("ARI-at-CIN-2026-06-13") == "ari-cin-1"
    assert normalize_game_id("ari-cin-1") == "ari-cin-1"
    assert normalize_game_id("ARI@CIN") == "ari-cin-1"
    assert normalize_game_id("ARI-CIN") == "ari-cin-1"
    assert normalize_game_id("ARI-CIN-2026-06-13") == "ari-cin-1"


def test_csv_provider_loads_watchlist_and_game_data_into_intake_models():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _csv_slate(root)
        provider = CSVDataProvider(root)

        watchlist = load_watchlist(provider)
        games = load_game_data(provider)

        assert watchlist.total_watchlist_batters == 1
        assert watchlist.batters[0].name == "TEX Watch Bat"
        assert watchlist.batters[0].bats == Handedness.R

        assert len(games) == 1
        game = games[0]
        assert game.game_id == "tex-kc-1"
        assert game.away_team.team == "KC"
        assert game.home_team.team == "TEX"
        assert game.home_team.batters[0].confirmed
        assert game.away_team.starting_pitcher.name == "KC Starter"
        assert game.environment.umpire.name == "Russ Zone"
        assert game.environment.park_hr_factor == 8.5
        assert game.weak_spots[0].pitcher_name == "KC Starter"
        assert game.hr_matchups[0].batter_name == "TEX Batter 1"
        assert validate_step2_intake(game).is_valid


def test_csv_provider_matches_mixed_game_id_formats_and_preserves_original_ids():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_csv(root, "watchlist", [{"game_id": "ARI@CIN", "name": "ARI Watch Bat", "team": "ARI", "lineup_slot": 4}])
        _write_csv(root, "lineups", _lineup_rows("ari-cin-1", "ARI", "L") + _lineup_rows("ARI@CIN", "CIN", "R"))
        _write_csv(
            root,
            "pitchers",
            [
                {"game_id": "ARI-CIN", "name": "ARI Starter", "team": "ARI", "throws": "R", "confirmed": "true"},
                {"game_id": "ARI-at-CIN-2026-06-13", "name": "CIN Starter", "team": "CIN", "throws": "L", "confirmed": "true"},
            ],
        )
        _write_csv(
            root,
            "weather",
            [
                {
                    "game_id": "ARI-at-CIN-2026-06-13",
                    "date": "2026-06-13",
                    "away_team": "ARI",
                    "home_team": "CIN",
                    "park": "Great American Ball Park",
                    "temperature_f": 84,
                }
            ],
        )
        _write_csv(root, "umpires", [{"game_id": "ARI-CIN", "name": "Russ Zone"}])
        _write_csv(root, "park_factors", [{"game_id": "ARI@CIN", "park_hr_factor": 9.0}])
        _write_csv(root, "weak_spots", [{"game_id": "ari-cin-1", "pitcher_name": "CIN Starter", "pitch": "fastball", "weakness_score": 7.0}])
        _write_csv(
            root,
            "hr_matchups",
            [
                {
                    "game_id": "ARI-at-CIN-2026-06-13",
                    "batter_name": "ARI Batter 4",
                    "pitcher_name": "CIN Starter",
                    "pitch": "fastball",
                    "matchup_score": 8.0,
                }
            ],
        )

        slate = load_daily_slate(CSVDataProvider(root), "2026-06-13")

        assert slate.game_ids == ["ari-cin-1"]
        game = slate.games[0]
        assert game.original_game_id
        assert game.environment.original_game_id == "ARI-at-CIN-2026-06-13"
        assert game.weak_spots[0].original_game_id == "ari-cin-1"
        assert game.hr_matchups[0].original_game_id == "ARI-at-CIN-2026-06-13"
        assert json.loads(slate.metadata["unmatched_game_ids"]) == {}
        assert validate_step2_intake(game).is_valid


def test_json_provider_loads_single_document_daily_slate_and_report_context():
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "slate.json"
        _json_slate(path)

        slate = load_daily_slate(JSONDataProvider(path))

        assert slate.date == "2026-06-13"
        assert slate.total_games == 1
        assert slate.watchlist.total_watchlist_batters == 1
        assert slate.games[0].home_team.team == "OAK"
        assert slate.games[0].environment.park_hr_factor == 5.8

        context = slate.to_report_context()
        assert context.report_date == "2026-06-13"
        assert context.games_reviewed == 1
        assert context.game_ids == ["sea-oak-1"]
        assert context.validation_status == "valid"


def test_connector_object_methods_match_top_level_loaders():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _csv_slate(root)
        connector = MLBDataConnector(CSVDataProvider(root))

        assert connector.load_watchlist().total_watchlist_batters == 1
        assert connector.load_game_data()[0].game_id == load_game_data(connector)[0].game_id
        assert connector.load_daily_slate("2026-06-13").to_report_context().validation_status == "valid"
