from __future__ import annotations

import json
from dataclasses import is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from russworks.providers import Provider, ProviderHealth, ProviderResult
from russworks.run import main as run_cli
from russworks.slate import LiveSlateBuilder, ProviderMappingConfig, SlateBuildResult, build_live_slate


class StaticSlateProvider(Provider):
    name = "static_slate"

    def __init__(self, records_by_dataset, *, fail_first: set[str] | None = None):
        self.records_by_dataset = records_by_dataset
        self.fail_first = set(fail_first or set())
        self.calls: dict[str, int] = {}

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        self.calls[dataset] = self.calls.get(dataset, 0) + 1
        if dataset in self.fail_first and self.calls[dataset] == 1:
            return ProviderResult(provider=self.name, dataset=dataset, success=False, errors=["temporary provider failure"])
        return ProviderResult(provider=self.name, dataset=dataset, records=list(self.records_by_dataset.get(dataset, [])))

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status="ok", checked_at="2026-06-13T00:00:00Z")


def _records():
    lineups = []
    watchlist = []
    for team in ["KC", "TEX"]:
        for slot in range(1, 10):
            row = {
                "game_id": "tex-kc-1",
                "name": f"{team} Batter {slot}",
                "team": team,
                "lineup_slot": slot,
                "bats": "R",
                "hr_pct": 10 + slot,
                "pitch_mix_score": 6,
                "confirmed": True,
                "tags": "Power",
            }
            lineups.append(row)
            if slot == 1:
                watchlist.append(row)
    return {
        "watchlist": watchlist,
        "lineups": lineups,
        "starting_pitchers": [
            {"game_id": "tex-kc-1", "name": "KC Starter", "team": "KC", "throws": "R", "projected_hr": 1.4, "confirmed": True},
            {"game_id": "tex-kc-1", "name": "TEX Starter", "team": "TEX", "throws": "L", "projected_hr": 1.6, "confirmed": True},
        ],
        "weather": [
            {
                "game_id": "tex-kc-1",
                "date": "2026-06-13",
                "away_team": "KC",
                "home_team": "TEX",
                "park": "Globe Life Field",
                "temperature_f": 90,
                "wind_mph": 9,
                "wind_direction": "out",
                "humidity_pct": 55,
                "roof": "open",
                "weather_hr_pct": 8,
                "weather_distance_ft": 12,
                "park_hr_factor": 8,
            }
        ],
        "umpires": [{"game_id": "tex-kc-1", "name": "Russ Zone", "zone_type": "Hitter", "run_lean": 1.2}],
        "park_factors": [{"game_id": "tex-kc-1", "park": "Globe Life Field", "park_hr_factor": 8}],
        "weak_spots": [
            {"game_id": "tex-kc-1", "pitcher_name": "KC Starter", "pitch": "slider", "weakness_score": 6},
            {"game_id": "tex-kc-1", "pitcher_name": "TEX Starter", "pitch": "fastball", "weakness_score": 6},
        ],
        "hr_matchups": [
            {"game_id": "tex-kc-1", "batter_name": "TEX Batter 1", "pitcher_name": "KC Starter", "pitch": "slider", "matchup_score": 8}
        ],
    }


def test_phase40_models_are_dataclasses():
    assert is_dataclass(ProviderMappingConfig)
    assert is_dataclass(SlateBuildResult)


def test_live_slate_builder_exports_canonical_csv_files_and_validates_exports():
    with TemporaryDirectory() as temp_dir:
        provider = StaticSlateProvider(_records())
        result = build_live_slate("2026-06-13", data_root=temp_dir, providers=[provider])

        assert result.success
        assert not result.partial
        assert result.record_counts["lineups"] == 18
        assert result.record_counts["pitchers"] == 2
        for dataset in ["watchlist", "lineups", "pitchers", "weather", "umpires", "park_factors", "weak_spots", "hr_matchups"]:
            assert Path(result.files_written[dataset]).exists()

        lineups = Path(result.files_written["lineups"]).read_text(encoding="utf-8")
        assert lineups.splitlines()[0].startswith("game_id,name,team,lineup_slot")


def test_live_slate_builder_reports_partial_slate_when_required_provider_data_is_missing():
    with TemporaryDirectory() as temp_dir:
        records = _records()
        records.pop("hr_matchups")
        result = build_live_slate("2026-06-13", data_root=temp_dir, providers=[StaticSlateProvider(records)])

        assert not result.success
        assert result.partial
        assert "hr_matchups" in result.missing_datasets
        assert "Missing required dataset: hr_matchups" in result.errors
        assert Path(result.files_written["hr_matchups"]).exists()


def test_live_slate_builder_retries_transient_provider_failures():
    with TemporaryDirectory() as temp_dir:
        provider = StaticSlateProvider(_records(), fail_first={"lineups"})
    result = build_live_slate("2026-06-13", data_root=temp_dir, providers=[provider], max_retries=1)

    assert result.success
    assert provider.calls["lineups"] == 2


def test_build_slate_flag_builds_csvs_before_daily_pipeline_run():
    with TemporaryDirectory() as temp_dir:
        data_root = Path(temp_dir) / "daily"
        output_root = Path(temp_dir) / "outputs"

        def fake_build_slate(date: str, *, data_root: str = "data/daily", providers=None, max_retries: int = 1):
            return build_live_slate(date, data_root=data_root, providers=[StaticSlateProvider(_records())], max_retries=max_retries)

        with patch("russworks.run.build_live_slate", side_effect=fake_build_slate):
            exit_code = run_cli(["--date", "2026-06-13", "--data-root", str(data_root), "--output-root", str(output_root), "--build-slate"])

        assert exit_code == 0
        assert (data_root / "2026-06-13" / "lineups.csv").exists()
        assert (output_root / "2026-06-13" / "russworks_full_report.json").exists()
        assert (output_root.parent / "dashboard" / "dashboard.json").exists()
        assert (output_root.parent / "command_center" / "command_center.json").exists()
        assert (output_root.parent / "web" / "dashboard_data.json").exists()
