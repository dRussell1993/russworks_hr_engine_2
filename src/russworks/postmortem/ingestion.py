from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping

from .models import ActualHomeRunEntry


class ActualHomeRunDataProvider(ABC):
    @abstractmethod
    def fetch_home_runs(self, date: str) -> List[Any]:
        raise NotImplementedError


class CSVHomeRunDataProvider(ActualHomeRunDataProvider):
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)

    def fetch_home_runs(self, date: str) -> List[dict[str, str]]:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Actual HR CSV not found: {self.csv_path}")
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return []
        return [row for row in rows if _row_matches_date(row, date)]


class MLBStatsHomeRunDataProvider(ActualHomeRunDataProvider):
    def fetch_home_runs(self, date: str) -> List[Any]:
        raise NotImplementedError(
            "MLB Stats live ingestion is a placeholder. Use CSVHomeRunDataProvider until a free API source is wired."
        )


class PostMortemIngestionRunner:
    def __init__(
        self,
        provider: ActualHomeRunDataProvider,
        output_dir: str | Path = "data/postmortem",
    ) -> None:
        self.provider = provider
        self.output_dir = Path(output_dir)

    def run(self, date: str) -> List[ActualHomeRunEntry]:
        raw_entries = self.provider.fetch_home_runs(date)
        normalized = [normalize_actual_home_run_entry(entry, date=date) for entry in raw_entries]
        self.save_normalized_entries(normalized, date)
        return normalized

    def save_normalized_entries(self, entries: Iterable[ActualHomeRunEntry], date: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"actual_home_runs_{date}.csv"
        fieldnames = [
            "team",
            "batter",
            "pitch",
            "pitcher",
            "inning",
            "exit_velocity",
            "distance",
            "angle",
            "metadata",
        ]
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(
                    {
                        "team": entry.team,
                        "batter": entry.batter,
                        "pitch": entry.pitch,
                        "pitcher": entry.pitcher,
                        "inning": entry.inning,
                        "exit_velocity": entry.exit_velocity,
                        "distance": entry.distance,
                        "angle": entry.angle,
                        "metadata": _metadata_to_text(entry.metadata),
                    }
                )
        return output_path


def normalize_actual_home_run_entry(raw: Any, date: str | None = None) -> ActualHomeRunEntry:
    data = _as_mapping(raw)
    metadata = {str(key): str(value) for key, value in data.items() if str(key).lower() not in _KNOWN_KEYS}
    if date:
        metadata.setdefault("date", date)
    return ActualHomeRunEntry(
        team=_required_text(data, "team", "Team", "batting_team", "club"),
        batter=_required_text(data, "batter", "Batter", "player", "player_name", "hitter"),
        pitch=_required_text(data, "pitch", "Pitch", "pitch_type", "pitchType"),
        pitcher=_required_text(data, "pitcher", "Pitcher", "opposing_pitcher", "pitcher_name"),
        inning=_required_int(data, "inning", "Inning"),
        exit_velocity=_required_float(data, "exit_velocity", "Exit Velocity", "exit_velo", "ev", "launch_speed"),
        distance=_required_float(data, "distance", "Distance", "hit_distance", "hit_distance_sc"),
        angle=_required_float(data, "angle", "Angle", "launch_angle", "la"),
        metadata=metadata,
    )


def default_csv_path(date: str, data_dir: str | Path = "data/postmortem") -> Path:
    return Path(data_dir) / f"actual_home_runs_raw_{date}.csv"


_KNOWN_KEYS = {
    "team",
    "batting_team",
    "club",
    "batter",
    "player",
    "player_name",
    "hitter",
    "pitch",
    "pitch_type",
    "pitchtype",
    "pitcher",
    "opposing_pitcher",
    "pitcher_name",
    "inning",
    "exit_velocity",
    "exit velo",
    "exit_velo",
    "ev",
    "launch_speed",
    "distance",
    "hit_distance",
    "hit_distance_sc",
    "angle",
    "launch_angle",
    "la",
    "date",
}


def _as_mapping(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, ActualHomeRunEntry):
        return asdict(raw)
    if is_dataclass(raw):
        return asdict(raw)
    if isinstance(raw, Mapping):
        return raw
    raise TypeError("Actual HR data must be a mapping, dataclass, or ActualHomeRunEntry.")


def _row_matches_date(row: Mapping[str, Any], date: str) -> bool:
    row_date = _optional_text(row, "date", "game_date", "Date")
    return not row_date or row_date == date


def _required_text(data: Mapping[str, Any], *keys: str) -> str:
    value = _first_present(data, *keys)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Actual HR entry missing required field: {keys[0]}")
    return str(value).strip()


def _optional_text(data: Mapping[str, Any], *keys: str) -> str:
    value = _first_present(data, *keys)
    return "" if value is None else str(value).strip()


def _required_int(data: Mapping[str, Any], *keys: str) -> int:
    value = _first_present(data, *keys)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Actual HR entry missing required field: {keys[0]}")
    return int(float(value))


def _required_float(data: Mapping[str, Any], *keys: str) -> float:
    value = _first_present(data, *keys)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Actual HR entry missing required field: {keys[0]}")
    return float(value)


def _first_present(data: Mapping[str, Any], *keys: str) -> Any:
    lower_map = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        if key in data:
            return data[key]
        lowered = key.lower()
        if lowered in lower_map:
            return lower_map[lowered]
    return None


def _metadata_to_text(metadata: Mapping[str, str]) -> str:
    return ";".join(f"{key}={value}" for key, value in sorted(metadata.items()))
