from dataclasses import is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.postmortem import (
    ActualHomeRunDataProvider,
    ActualHomeRunEntry,
    CSVHomeRunDataProvider,
    MLBStatsHomeRunDataProvider,
    PostMortemNotReady,
    PostMortemIngestionRunner,
    default_csv_path,
    normalize_actual_home_run_entry,
)
from russworks.postmortem.ingestion import ActualHomeRunDataProvider as ProviderBase
from russworks.postmortem.run import main as postmortem_ingestion_main


FIXTURE_CSV = Path("tests/fixtures/postmortem_actual_home_runs.csv")


def test_provider_classes_are_exported():
    assert ActualHomeRunDataProvider is ProviderBase
    assert issubclass(CSVHomeRunDataProvider, ActualHomeRunDataProvider)
    assert issubclass(MLBStatsHomeRunDataProvider, ActualHomeRunDataProvider)


def test_csv_provider_filters_by_date_and_preserves_duplicate_batter_rows():
    rows = CSVHomeRunDataProvider(FIXTURE_CSV).fetch_home_runs("2026-06-13")

    assert len(rows) == 3
    assert sum(1 for row in rows if row["batter"] == "KC Hidden Value") == 2
    assert all(row["date"] == "2026-06-13" for row in rows)


def test_normalize_actual_home_run_entry_supports_aliases_and_metadata():
    entry = normalize_actual_home_run_entry(
        {
            "club": "TEX",
            "player_name": "TEX YPI Bat",
            "pitch_type": "slider",
            "pitcher_name": "KC Starter",
            "Inning": "2",
            "Exit Velocity": "106.2",
            "hit_distance": "411",
            "launch_angle": "28",
            "game_id": "tex-kc-1",
        },
        date="2026-06-13",
    )

    assert is_dataclass(entry)
    assert isinstance(entry, ActualHomeRunEntry)
    assert entry.team == "TEX"
    assert entry.batter == "TEX YPI Bat"
    assert entry.inning == 2
    assert entry.exit_velocity == 106.2
    assert entry.metadata["game_id"] == "tex-kc-1"
    assert entry.metadata["date"] == "2026-06-13"


def test_ingestion_runner_saves_normalized_file_to_postmortem_directory():
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "data" / "postmortem"
        runner = PostMortemIngestionRunner(
            provider=CSVHomeRunDataProvider(FIXTURE_CSV),
            output_dir=output_dir,
        )

        entries = runner.run("2026-06-13")
        output_path = output_dir / "actual_home_runs_2026-06-13.csv"

        assert len(entries) == 3
        assert sum(1 for entry in entries if entry.batter == "KC Hidden Value") == 2
        assert output_path.exists()
        saved = output_path.read_text(encoding="utf-8")
        assert "TEX YPI Bat" in saved
        assert saved.count("KC Hidden Value") == 2


def test_mlb_stats_provider_fetches_final_game_home_runs():
    provider = MLBStatsHomeRunDataProvider(requester=_mlb_stats_requester(final=True))

    rows = provider.fetch_home_runs("2026-06-13")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-13"
    assert rows[0]["game_id"] == "12345"
    assert rows[0]["batter"] == "TEX YPI Bat"
    assert rows[0]["team"] == "TEX"
    assert rows[0]["opponent"] == "KC"
    assert rows[0]["pitcher"] == "KC Starter"
    assert rows[0]["inning"] == 2
    assert rows[0]["exit_velocity"] == 106.2


def test_mlb_stats_provider_reports_not_ready_for_non_final_games():
    provider = MLBStatsHomeRunDataProvider(requester=_mlb_stats_requester(final=False))

    try:
        provider.fetch_home_runs("2026-06-13")
        assert False, "non-final MLB games should block post-mortem acquisition"
    except PostMortemNotReady as exc:
        assert str(exc) == "Postmortem not ready."


def test_mlb_stats_entries_normalize_with_game_and_opponent_metadata():
    provider = MLBStatsHomeRunDataProvider(requester=_mlb_stats_requester(final=True))

    entry = normalize_actual_home_run_entry(provider.fetch_home_runs("2026-06-13")[0], date="2026-06-13")

    assert entry.batter == "TEX YPI Bat"
    assert entry.pitch == "Slider"
    assert entry.metadata["game_id"] == "12345"
    assert entry.metadata["opponent"] == "KC"


def test_default_csv_path_uses_postmortem_data_directory():
    assert default_csv_path("2026-06-13") == Path("data/postmortem/actual_home_runs_raw_2026-06-13.csv")


def test_cli_ingests_manual_csv_import():
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "data" / "postmortem"
        code = postmortem_ingestion_main(
            [
                "--date",
                "2026-06-13",
                "--csv",
                str(FIXTURE_CSV),
                "--output-dir",
                str(output_dir),
            ]
        )

        assert code == 0
        output_path = output_dir / "actual_home_runs_2026-06-13.csv"
        assert output_path.exists()
        assert "KC Hidden Value" in output_path.read_text(encoding="utf-8")


def _mlb_stats_requester(*, final: bool):
    def requester(url: str, timeout_seconds: float):
        if "/schedule" in url:
            return {
                "dates": [
                    {
                        "games": [
                            {
                                "gamePk": 12345,
                                "status": {
                                    "abstractGameState": "Final" if final else "Live",
                                    "detailedState": "Final" if final else "In Progress",
                                },
                            }
                        ]
                    }
                ]
            }
        if "/game/12345/feed/live" in url:
            return {
                "gameData": {
                    "teams": {
                        "away": {"abbreviation": "TEX"},
                        "home": {"abbreviation": "KC"},
                    }
                },
                "liveData": {
                    "plays": {
                        "allPlays": [
                            {
                                "result": {"eventType": "single", "event": "Single"},
                                "about": {"inning": 1, "halfInning": "top"},
                            },
                            {
                                "result": {"eventType": "home_run", "event": "Home Run"},
                                "about": {"inning": 2, "halfInning": "top"},
                                "matchup": {
                                    "batter": {"fullName": "TEX YPI Bat"},
                                    "pitcher": {"fullName": "KC Starter"},
                                },
                                "playEvents": [
                                    {
                                        "details": {"type": {"description": "Slider", "code": "SL"}},
                                        "hitData": {"launchSpeed": 106.2, "totalDistance": 411, "launchAngle": 28},
                                    }
                                ],
                            },
                        ]
                    }
                },
            }
        raise AssertionError(f"unexpected URL: {url}")

    return requester
