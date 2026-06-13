from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from russworks.data import CSVDataProvider, load_daily_slate
from russworks.providers import BallparkProvider, BaseballSavantProvider, MLBStatsProvider, Provider, ProviderResult, WeatherProvider


Record = dict[str, Any]


DATASET_ORDER = [
    "watchlist",
    "lineups",
    "starting_pitchers",
    "probable_pitchers",
    "weather",
    "umpires",
    "park_factors",
    "weak_spots",
    "hr_matchups",
]


OUTPUT_DATASETS = [
    "watchlist",
    "lineups",
    "pitchers",
    "weather",
    "umpires",
    "park_factors",
    "weak_spots",
    "hr_matchups",
]


CSV_HEADERS = {
    "watchlist": ["name", "team", "bats", "lineup_slot", "hr_pct", "pitch_mix_score", "projected_ab", "projected_hits", "fair_odds", "book_odds", "tags", "confirmed"],
    "lineups": ["game_id", "name", "team", "lineup_slot", "bats", "hr_pct", "pitch_mix_score", "confirmed", "tags"],
    "pitchers": ["game_id", "name", "team", "throws", "tags", "projected_ip", "projected_hits", "projected_hr", "projected_bb", "projected_er", "projected_outs", "confirmed"],
    "weather": ["game_id", "date", "away_team", "home_team", "park", "temperature_f", "wind_mph", "wind_direction", "humidity_pct", "roof", "weather_hr_pct", "weather_distance_ft", "park_hr_factor"],
    "umpires": ["game_id", "name", "zone_type", "called_strike_rate", "accuracy", "consistency", "run_lean"],
    "park_factors": ["game_id", "park", "park_hr_factor", "left_field_carry", "center_field_carry", "right_field_carry"],
    "weak_spots": ["game_id", "pitcher_name", "pitch", "zone", "weakness_score", "notes"],
    "hr_matchups": ["game_id", "batter_name", "pitcher_name", "pitch", "matchup_score", "exit_velo", "angle", "distance", "notes"],
}


@dataclass(frozen=True)
class ProviderMappingConfig:
    data_root: str = "data/daily"
    required_datasets: tuple[str, ...] = ("lineups", "pitchers", "weather", "umpires", "park_factors", "weak_spots", "hr_matchups")
    optional_datasets: tuple[str, ...] = ("watchlist",)
    max_retries: int = 1
    write_empty_files: bool = True


@dataclass(frozen=True)
class SlateBuildResult:
    date: str
    output_dir: str
    success: bool
    partial: bool
    files_written: dict[str, str] = field(default_factory=dict)
    record_counts: dict[str, int] = field(default_factory=dict)
    provider_results: list[dict[str, Any]] = field(default_factory=list)
    provider_health: list[dict[str, Any]] = field(default_factory=list)
    missing_datasets: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class LiveSlateBuilder:
    def __init__(
        self,
        *,
        providers: Sequence[Provider] | None = None,
        config: ProviderMappingConfig | None = None,
    ) -> None:
        self.providers = list(providers) if providers is not None else [
            MLBStatsProvider(),
            WeatherProvider(),
            BallparkProvider(),
            BaseballSavantProvider(),
        ]
        self.config = config or ProviderMappingConfig()

    def build_slate(self, date: str) -> SlateBuildResult:
        output_dir = Path(self.config.data_root) / date
        collected, provider_results, warnings = self._collect_provider_records(date)
        exports = self._records_for_export(collected)
        files_written = self._write_exports(output_dir, exports)
        record_counts = {dataset: len(records) for dataset, records in exports.items()}
        missing = [dataset for dataset in self.config.required_datasets if record_counts.get(dataset, 0) == 0]
        validation_errors = self._validate_exports(output_dir, date)
        errors = [f"Missing required dataset: {dataset}" for dataset in missing]
        errors.extend(validation_errors)
        health = [provider.health() for provider in self.providers]
        return SlateBuildResult(
            date=date,
            output_dir=str(output_dir),
            success=not errors,
            partial=bool(missing or validation_errors),
            files_written=files_written,
            record_counts=record_counts,
            provider_results=[_provider_result_row(result) for result in provider_results],
            provider_health=[_json_ready(asdict(item)) for item in health],
            missing_datasets=missing,
            validation_errors=validation_errors,
            errors=errors,
            warnings=warnings,
        )

    def _collect_provider_records(self, slate_date: str) -> tuple[dict[str, list[Record]], list[ProviderResult], list[str]]:
        records_by_dataset = {dataset: [] for dataset in DATASET_ORDER}
        results: list[ProviderResult] = []
        warnings: list[str] = []
        for dataset in DATASET_ORDER:
            result = self._fetch_dataset(dataset, slate_date)
            results.append(result)
            if result.success and result.records:
                records_by_dataset[dataset].extend(dict(record) for record in result.records)
            elif result.errors:
                warnings.extend(f"{result.provider}:{dataset}: {error}" for error in result.errors)
        return records_by_dataset, results, warnings

    def _fetch_dataset(self, dataset: str, slate_date: str) -> ProviderResult:
        errors: list[str] = []
        for provider in self.providers:
            for attempt in range(self.config.max_retries + 1):
                result = provider.fetch_dataset(dataset, slate_date)
                if result.success and result.records:
                    return result
                if result.errors:
                    errors.extend(f"{provider.name}: {error}" for error in result.errors)
                if result.success or not _retryable_result(result):
                    break
                if attempt >= self.config.max_retries:
                    break
        return ProviderResult(provider="none", dataset=dataset, records=[], success=False, errors=errors or ["no provider records"])

    def _records_for_export(self, collected: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[Record]]:
        return {
            "watchlist": [_batter_row(record, include_game_id=False) for record in collected.get("watchlist", [])],
            "lineups": [_batter_row(record, include_game_id=True) for record in collected.get("lineups", [])],
            "pitchers": [
                _pitcher_row(record)
                for dataset in ("starting_pitchers", "probable_pitchers")
                for record in collected.get(dataset, [])
            ],
            "weather": [_weather_row(record) for record in collected.get("weather", [])],
            "umpires": [_umpire_row(record) for record in collected.get("umpires", [])],
            "park_factors": [_park_factor_row(record) for record in collected.get("park_factors", [])],
            "weak_spots": [_weak_spot_row(record) for record in collected.get("weak_spots", [])],
            "hr_matchups": [_hr_matchup_row(record) for record in collected.get("hr_matchups", [])],
        }

    def _write_exports(self, output_dir: Path, exports: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for dataset in OUTPUT_DATASETS:
            rows = list(exports.get(dataset, []))
            if not rows and not self.config.write_empty_files:
                continue
            path = output_dir / f"{dataset}.csv"
            _write_csv(path, CSV_HEADERS[dataset], rows)
            files[dataset] = str(path)
        return files

    def _validate_exports(self, output_dir: Path, slate_date: str) -> list[str]:
        try:
            slate = load_daily_slate(CSVDataProvider(output_dir), slate_date)
        except Exception as exc:
            return [f"Export validation failed: {exc}"]
        errors: list[str] = []
        if not slate.games:
            errors.append("Export validation failed: no games were built from exported CSV files.")
        return errors


def build_live_slate(
    date: str,
    *,
    data_root: str = "data/daily",
    providers: Sequence[Provider] | None = None,
    max_retries: int = 1,
) -> SlateBuildResult:
    config = ProviderMappingConfig(data_root=data_root, max_retries=max_retries)
    return LiveSlateBuilder(providers=providers, config=config).build_slate(date)


def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: _csv_value(row.get(header, "")) for header in headers})


def _provider_result_row(result: ProviderResult) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "dataset": result.dataset,
        "success": result.success,
        "record_count": len(result.records),
        "errors": list(result.errors),
        "metadata": dict(result.metadata),
    }


def _retryable_result(result: ProviderResult) -> bool:
    text = " ".join(result.errors).lower()
    if "does not support dataset" in text:
        return False
    if "provider not configured" in text or "missing base url" in text:
        return False
    return not result.success


def _batter_row(record: Mapping[str, Any], *, include_game_id: bool) -> Record:
    row = {
        "name": _first(record, "name", "batter", "batter_name", "player_name", "fullName"),
        "team": _first(record, "team", "team_abbrev", "club"),
        "bats": _first(record, "bats", "handedness"),
        "lineup_slot": _first(record, "lineup_slot", "slot", "batting_order"),
        "hr_pct": _first(record, "hr_pct", "hr_percent", "hr_probability", default=0.0),
        "pitch_mix_score": _first(record, "pitch_mix_score", "pitch_fit", default=0.0),
        "projected_ab": _first(record, "projected_ab", "ab", default=4),
        "projected_hits": _first(record, "projected_hits", "hits", default=0.0),
        "fair_odds": _first(record, "fair_odds", default=""),
        "book_odds": _first(record, "book_odds", "odds", default=""),
        "tags": _tags(_first(record, "tags", default="")),
        "confirmed": _first(record, "confirmed", default=True),
    }
    if include_game_id:
        return {"game_id": _first(record, "game_id", "gamePk", "game"), **row}
    return row


def _pitcher_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "name": _first(record, "name", "pitcher", "pitcher_name", "fullName"),
        "team": _first(record, "team", "team_abbrev", "club"),
        "throws": _first(record, "throws", "handedness", default="UNKNOWN"),
        "tags": _tags(_first(record, "tags", default="")),
        "projected_ip": _first(record, "projected_ip", "ip", default=0.0),
        "projected_hits": _first(record, "projected_hits", "hits", default=0.0),
        "projected_hr": _first(record, "projected_hr", "hr", default=0.0),
        "projected_bb": _first(record, "projected_bb", "walks", "bb", default=0.0),
        "projected_er": _first(record, "projected_er", "er", default=0.0),
        "projected_outs": _first(record, "projected_outs", "outs", default=0.0),
        "confirmed": _first(record, "confirmed", default=True),
    }


def _weather_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "date": _first(record, "date"),
        "away_team": _first(record, "away_team", "away"),
        "home_team": _first(record, "home_team", "home"),
        "park": _first(record, "park", "park_name", "venue", "ballpark"),
        "temperature_f": _first(record, "temperature_f", "temperature", "temp_f", default=70.0),
        "wind_mph": _first(record, "wind_mph", "wind_speed", default=0.0),
        "wind_direction": _first(record, "wind_direction", default=""),
        "humidity_pct": _first(record, "humidity_pct", "humidity", default=0.0),
        "roof": _first(record, "roof", "roof_status", default="open"),
        "weather_hr_pct": _first(record, "weather_hr_pct", "weather_boost", default=0.0),
        "weather_distance_ft": _first(record, "weather_distance_ft", "distance_boost", default=0.0),
        "park_hr_factor": _first(record, "park_hr_factor", "hr_park_factor", default=0.0),
    }


def _umpire_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "name": _first(record, "name", "umpire", "umpire_name", "fullName"),
        "zone_type": _first(record, "zone_type", default="Neutral"),
        "called_strike_rate": _first(record, "called_strike_rate", default=0.0),
        "accuracy": _first(record, "accuracy", default=0.0),
        "consistency": _first(record, "consistency", default=0.0),
        "run_lean": _first(record, "run_lean", default=0.0),
    }


def _park_factor_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "park": _first(record, "park", "park_name", "venue"),
        "park_hr_factor": _first(record, "park_hr_factor", "hr_park_factor", default=0.0),
        "left_field_carry": _first(record, "left_field_carry", default=0.0),
        "center_field_carry": _first(record, "center_field_carry", default=0.0),
        "right_field_carry": _first(record, "right_field_carry", default=0.0),
    }


def _weak_spot_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "pitcher_name": _first(record, "pitcher_name", "pitcher"),
        "pitch": _first(record, "pitch", "pitch_type"),
        "zone": _first(record, "zone", default=""),
        "weakness_score": _first(record, "weakness_score", "score", default=0.0),
        "notes": _first(record, "notes", default=""),
    }


def _hr_matchup_row(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "batter_name": _first(record, "batter_name", "batter"),
        "pitcher_name": _first(record, "pitcher_name", "pitcher"),
        "pitch": _first(record, "pitch", "pitch_type"),
        "matchup_score": _first(record, "matchup_score", "score", default=0.0),
        "exit_velo": _first(record, "exit_velo", "exit_velocity", default=""),
        "angle": _first(record, "angle", "launch_angle", default=""),
        "distance": _first(record, "distance", default=""),
        "notes": _first(record, "notes", default=""),
    }


def _first(record: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        if key in record and record[key] is not None and record[key] != "":
            return record[key]
        lowered_key = key.lower()
        if lowered_key in lowered and lowered[lowered_key] is not None and lowered[lowered_key] != "":
            return lowered[lowered_key]
    return default


def _tags(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item).strip() for item in value if str(item).strip())
    return str(value).replace(",", "|").replace(";", "|")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
