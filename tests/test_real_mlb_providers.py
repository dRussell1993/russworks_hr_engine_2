from dataclasses import is_dataclass
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.data import CSVDataProvider
from russworks.pipeline import DailyRunRequest, run_daily_pipeline
from russworks.providers import (
    BallparkProvider,
    BaseballSavantProvider,
    DailySlateProvider,
    InMemoryDataProvider,
    MLBStatsProvider,
    Provider,
    ProviderHealth,
    ProviderResult,
    RateLimitError,
    WeatherProvider,
)


class StaticProvider(Provider):
    name = "static"

    def __init__(self, records_by_dataset):
        self.records_by_dataset = records_by_dataset

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        return ProviderResult(provider=self.name, dataset=dataset, records=list(self.records_by_dataset.get(dataset, [])))

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status="ok", checked_at="2026-06-13T00:00:00Z")


def _records():
    lineups = []
    for team in ["KC", "TEX"]:
        for slot in range(1, 10):
            lineups.append(
                {
                    "game_id": "tex-kc-1",
                    "name": f"{team} Batter {slot}",
                    "team": team,
                    "lineup_slot": slot,
                    "bats": "R",
                    "hr_pct": 10 + slot,
                    "confirmed": True,
                }
            )
    return {
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
                "weather_hr_pct": 8,
                "weather_distance_ft": 12,
                "park_hr_factor": 8,
            }
        ],
        "umpires": [{"game_id": "tex-kc-1", "name": "Russ Zone", "zone_type": "Hitter", "run_lean": 1.2}],
        "park_factors": [{"game_id": "tex-kc-1", "park_hr_factor": 8}],
        "weak_spots": [
            {"game_id": "tex-kc-1", "pitcher_name": "KC Starter", "pitch": "slider", "weakness_score": 6},
            {"game_id": "tex-kc-1", "pitcher_name": "TEX Starter", "pitch": "fastball", "weakness_score": 6},
        ],
        "hr_matchups": [
            {"game_id": "tex-kc-1", "batter_name": "TEX Batter 1", "pitcher_name": "KC Starter", "pitch": "slider", "matchup_score": 8}
        ],
    }


def _write_csv(root: Path, name: str, header: list[str], rows: list[list[object]]) -> None:
    path = root / f"{name}.csv"
    path.write_text("\n".join([",".join(header), *[",".join(str(value) for value in row) for row in rows]]), encoding="utf-8")


def _write_fallback_csv(root: Path) -> None:
    records = _records()
    _write_csv(root, "watchlist", ["name", "team"], [["TEX Watch", "TEX"]])
    _write_csv(root, "weak_spots", ["game_id", "pitcher_name", "pitch", "weakness_score"], [[r["game_id"], r["pitcher_name"], r["pitch"], r["weakness_score"]] for r in records["weak_spots"]])
    _write_csv(root, "hr_matchups", ["game_id", "batter_name", "pitcher_name", "pitch", "matchup_score"], [[r["game_id"], r["batter_name"], r["pitcher_name"], r["pitch"], r["matchup_score"]] for r in records["hr_matchups"]])


def test_phase20_provider_models_are_dataclasses():
    assert is_dataclass(ProviderResult)
    assert is_dataclass(ProviderHealth)


def test_live_providers_report_not_configured_without_env_vars():
    provider = MLBStatsProvider()
    result = provider.fetch_lineups("2026-06-13")
    health = provider.health()

    assert not result.success
    assert "RUSSWORKS_MLB_STATS_BASE_URL" in result.errors[0]
    assert health.status == "not_configured"


def test_daily_slate_provider_combines_live_records_and_fallback_validation_inputs():
    with TemporaryDirectory() as temp_dir:
        fallback_root = Path(temp_dir)
        _write_fallback_csv(fallback_root)
        live_records = _records()
        provider = DailySlateProvider(
            providers=[StaticProvider({key: value for key, value in live_records.items() if key not in {"weak_spots", "hr_matchups"}})],
            fallback_provider=CSVDataProvider(fallback_root),
        )

        slate = provider.load_daily_slate("2026-06-13")

        assert slate.total_games == 1
        assert slate.games[0].away_team.team == "KC"
        assert len(slate.games[0].home_team.batters) == 9
        assert slate.games[0].weak_spots
        assert slate.games[0].hr_matchups
        assert "provider_statuses" in slate.metadata


def test_provider_retry_logic_recovers_after_rate_limit():
    calls = {"count": 0}

    def requester(url, headers, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RateLimitError("slow down")
        return {"records": [{"game_id": "1", "name": "Batter", "team": "TEX", "lineup_slot": 1}]}

    previous = os.environ.get("RUSSWORKS_MLB_STATS_BASE_URL")
    os.environ["RUSSWORKS_MLB_STATS_BASE_URL"] = "https://example.test"
    try:
        provider = MLBStatsProvider(requester=requester, min_interval_seconds=0.0, max_retries=1)

        result = provider.fetch_lineups("2026-06-13")

        assert result.success
        assert calls["count"] == 2
        assert provider.health().status == "ok"
    finally:
        if previous is None:
            os.environ.pop("RUSSWORKS_MLB_STATS_BASE_URL", None)
        else:
            os.environ["RUSSWORKS_MLB_STATS_BASE_URL"] = previous


def test_source_specific_providers_support_expected_datasets():
    def requester(url, headers, timeout):
        return {"records": [{"game_id": "tex-kc-1", "park": "Globe Life Field", "park_hr_factor": 8}]}

    previous = {
        "RUSSWORKS_WEATHER_BASE_URL": os.environ.get("RUSSWORKS_WEATHER_BASE_URL"),
        "RUSSWORKS_BALLPARK_BASE_URL": os.environ.get("RUSSWORKS_BALLPARK_BASE_URL"),
        "RUSSWORKS_BASEBALL_SAVANT_BASE_URL": os.environ.get("RUSSWORKS_BASEBALL_SAVANT_BASE_URL"),
    }
    os.environ["RUSSWORKS_WEATHER_BASE_URL"] = "https://weather.test"
    os.environ["RUSSWORKS_BALLPARK_BASE_URL"] = "https://park.test"
    os.environ["RUSSWORKS_BASEBALL_SAVANT_BASE_URL"] = "https://savant.test"
    try:
        assert WeatherProvider(requester=requester, min_interval_seconds=0).fetch_weather("2026-06-13").success
        assert BallparkProvider(requester=requester, min_interval_seconds=0).fetch_ballparks("2026-06-13").success
        assert BaseballSavantProvider(requester=requester, min_interval_seconds=0).fetch_weak_spots("2026-06-13").success
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_daily_pipeline_live_mode_preserves_provider_metadata():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        day = root / "daily" / "2026-06-13"
        day.mkdir(parents=True)
        records = _records()
        dataset_names = ["lineups", "starting_pitchers", "weather", "umpires", "park_factors", "weak_spots", "hr_matchups"]
        csv_names = {"starting_pitchers": "pitchers"}
        for name in dataset_names:
            rows = records[name]
            header = list(rows[0].keys())
            _write_csv(day, csv_names.get(name, name), header, [[row[key] for key in header] for row in rows])
        _write_csv(day, "watchlist", ["name", "team"], [["TEX Watch", "TEX"]])

        result = run_daily_pipeline(
            "2026-06-13",
            data_root=str(root / "daily"),
            output_root=str(root / "outputs"),
            provider_mode="live",
        )

        assert result.success
        assert "provider_statuses" in result.slate.metadata
        assert result.validation_status == "valid"
