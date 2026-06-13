from dataclasses import is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.postmortem import (
    ActualHomeRunDataProvider,
    ActualHomeRunEntry,
    CSVHomeRunDataProvider,
    MLBStatsHomeRunDataProvider,
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


def test_mlb_stats_provider_is_placeholder_without_paid_keys():
    provider = MLBStatsHomeRunDataProvider()

    try:
        provider.fetch_home_runs("2026-06-13")
        assert False, "MLB stats placeholder should not fetch yet"
    except NotImplementedError as exc:
        assert "placeholder" in str(exc).lower()
        assert "CSVHomeRunDataProvider" in str(exc)


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
