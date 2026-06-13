from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, WatchlistImport
from russworks.intake import validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.reports import ReportContext


Record = dict[str, Any]
_TEAM_CODE = re.compile(r"^[a-z]{2,3}$")


@dataclass(frozen=True)
class DailySlate:
    date: str
    games: list[GameIntake] = field(default_factory=list)
    watchlist: WatchlistImport = field(default_factory=WatchlistImport)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def total_games(self) -> int:
        return len(self.games)

    @property
    def game_ids(self) -> list[str]:
        return [game.game_id for game in self.games]

    def to_report_context(self) -> ReportContext:
        statuses = [validate_step2_intake(game).is_valid for game in self.games]
        if not statuses:
            validation_status = "no_games"
        elif all(statuses):
            validation_status = "valid"
        elif any(statuses):
            validation_status = "partial"
        else:
            validation_status = "invalid"
        return ReportContext(
            report_date=self.date,
            games_reviewed=self.total_games,
            validation_status=validation_status,
            game_ids=self.game_ids,
            validation_summary={
                "total_games": self.total_games,
                "complete_games": sum(1 for status in statuses if status),
                "invalid_games": sum(1 for status in statuses if not status),
            },
            notes=[f"watchlist_batters={self.watchlist.total_watchlist_batters}"],
        )


class DataProvider(ABC):
    @abstractmethod
    def load_records(self, dataset: str) -> list[Record]:
        raise NotImplementedError


class CSVDataProvider(DataProvider):
    def __init__(self, root: str | Path, *, file_map: Mapping[str, str | Path] | None = None) -> None:
        self.root = Path(root)
        self.file_map = dict(file_map or {})

    def load_records(self, dataset: str) -> list[Record]:
        path = self._dataset_path(dataset)
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [_clean_record(row) for row in csv.DictReader(handle)]

    def _dataset_path(self, dataset: str) -> Path:
        mapped = self.file_map.get(dataset)
        if mapped is not None:
            path = Path(mapped)
            return path if path.is_absolute() else self.root / path
        return self.root / f"{dataset}.csv"


class JSONDataProvider(DataProvider):
    def __init__(self, source: str | Path, *, file_map: Mapping[str, str | Path] | None = None) -> None:
        self.source = Path(source)
        self.file_map = dict(file_map or {})
        self._document: Any | None = None

    def load_records(self, dataset: str) -> list[Record]:
        if self.source.is_dir() or self.file_map:
            path = self._dataset_path(dataset)
            if not path.exists():
                return []
            return _records_from_json(_load_json(path), dataset)
        document = self._load_document()
        if isinstance(document, dict):
            payload = document.get(dataset, document.get(_plural(dataset), []))
            return _records_from_json(payload, dataset)
        return _records_from_json(document, dataset)

    def _dataset_path(self, dataset: str) -> Path:
        mapped = self.file_map.get(dataset)
        if mapped is not None:
            path = Path(mapped)
            return path if path.is_absolute() else self.source / path
        return self.source / f"{dataset}.json"

    def _load_document(self) -> Any:
        if self._document is None:
            self._document = _load_json(self.source)
        return self._document


class WatchlistProvider:
    def __init__(self, data_provider: DataProvider) -> None:
        self.data_provider = data_provider

    def load_watchlist(self) -> WatchlistImport:
        batters = [_batter_from_record(row, confirmed=_bool(_value(row, "confirmed", default=False))) for row in self.data_provider.load_records("watchlist")]
        return WatchlistImport(batters=[batter for batter in batters if batter.requires_review])


class LineupProvider:
    def __init__(self, data_provider: DataProvider) -> None:
        self.data_provider = data_provider

    def load_lineups(self) -> dict[str, dict[str, list[BatterIntake]]]:
        lineups: dict[str, dict[str, list[BatterIntake]]] = {}
        for row in self.data_provider.load_records("lineups"):
            game_id, _ = _game_id_from_record(row)
            team = str(_value(row, "team", default="")).strip()
            if not game_id or not team:
                continue
            lineups.setdefault(game_id, {}).setdefault(team, []).append(_batter_from_record(row, confirmed=True, source="lineup"))
        return lineups


class PitcherProvider:
    def __init__(self, data_provider: DataProvider) -> None:
        self.data_provider = data_provider

    def load_pitchers(self) -> dict[str, dict[str, PitcherIntake]]:
        pitchers: dict[str, dict[str, PitcherIntake]] = {}
        for row in self.data_provider.load_records("pitchers"):
            game_id, _ = _game_id_from_record(row)
            team = str(_value(row, "team", default="")).strip()
            if not game_id or not team:
                continue
            pitchers.setdefault(game_id, {})[team] = PitcherIntake(
                name=str(_value(row, "name", "pitcher", "pitcher_name", default="")).strip(),
                team=team,
                throws=_handedness(_value(row, "throws", "handedness", default="UNKNOWN")),
                tags=_tags(_value(row, "tags", default="")),
                projected_ip=_float(_value(row, "projected_ip", "ip", default=0.0)),
                projected_hits=_float(_value(row, "projected_hits", "hits", default=0.0)),
                projected_hr=_float(_value(row, "projected_hr", "hr", default=0.0)),
                projected_bb=_float(_value(row, "projected_bb", "bb", "walks", default=0.0)),
                projected_er=_float(_value(row, "projected_er", "er", default=0.0)),
                projected_outs=_float(_value(row, "projected_outs", "outs", default=0.0)),
                confirmed=_bool(_value(row, "confirmed", default=True)),
            )
        return pitchers


class EnvironmentProvider:
    def __init__(self, data_provider: DataProvider) -> None:
        self.data_provider = data_provider

    def load_environments(self) -> dict[str, GameEnvironment]:
        umpires = self.load_umpires()
        park_factors = self.load_park_factors()
        environments: dict[str, GameEnvironment] = {}
        for row in self.data_provider.load_records("weather"):
            game_id, original_game_id = _game_id_from_record(row)
            if not game_id:
                continue
            park = str(_value(row, "park", "park_name", default="")).strip()
            park_factor = park_factors.get(game_id, _float(_value(row, "park_hr_factor", "hr_park_factor", default=0.0)))
            environments[game_id] = GameEnvironment(
                game_id=game_id,
                date=str(_value(row, "date", default="")).strip(),
                away_team=str(_value(row, "away_team", default="")).strip(),
                home_team=str(_value(row, "home_team", default="")).strip(),
                park=park,
                temperature_f=_float(_value(row, "temperature_f", "temperature", default=70.0)),
                wind_mph=_float(_value(row, "wind_mph", "wind_speed", default=0.0)),
                wind_direction=str(_value(row, "wind_direction", default="")).strip(),
                humidity_pct=_float(_value(row, "humidity_pct", "humidity", default=0.0)),
                roof=str(_value(row, "roof", "roof_status", default="open")).strip() or "open",
                weather_hr_pct=_float(_value(row, "weather_hr_pct", "weather_boost", default=0.0)),
                weather_distance_ft=_float(_value(row, "weather_distance_ft", "weather_distance", default=0.0)),
                park_hr_factor=park_factor,
                umpire=umpires.get(game_id),
                original_game_id=original_game_id,
            )
        return environments

    def load_umpires(self) -> dict[str, Umpire]:
        umpires: dict[str, Umpire] = {}
        for row in self.data_provider.load_records("umpires"):
            game_id, _ = _game_id_from_record(row)
            if not game_id:
                continue
            umpires[game_id] = Umpire(
                name=str(_value(row, "name", "umpire", "umpire_name", default="")).strip(),
                zone_type=str(_value(row, "zone_type", default="Neutral")).strip() or "Neutral",
                called_strike_rate=_float(_value(row, "called_strike_rate", default=0.0)),
                accuracy=_float(_value(row, "accuracy", default=0.0)),
                consistency=_float(_value(row, "consistency", default=0.0)),
                run_lean=_float(_value(row, "run_lean", default=0.0)),
            )
        return umpires

    def load_park_factors(self) -> dict[str, float]:
        factors: dict[str, float] = {}
        for row in self.data_provider.load_records("park_factors"):
            game_id, _ = _game_id_from_record(row)
            if game_id:
                factors[game_id] = _float(_value(row, "park_hr_factor", "hr_park_factor", default=0.0))
        return factors


class MLBDataConnector(WatchlistProvider, LineupProvider, PitcherProvider, EnvironmentProvider):
    def __init__(self, data_provider: DataProvider) -> None:
        WatchlistProvider.__init__(self, data_provider)

    def load_game_data(self) -> list[GameIntake]:
        lineups = self.load_lineups()
        pitchers = self.load_pitchers()
        environments = self.load_environments()
        weak_spot_rows = self.data_provider.load_records("weak_spots")
        hr_matchup_rows = self.data_provider.load_records("hr_matchups")
        weak_spots = _weak_spots_by_game(weak_spot_rows)
        hr_matchups = _hr_matchups_by_game(hr_matchup_rows)
        game_ids = sorted(set(lineups) | set(pitchers) | set(environments))
        original_game_ids = _original_game_ids_by_normalized(
            [
                *self.data_provider.load_records("lineups"),
                *self.data_provider.load_records("pitchers"),
                *self.data_provider.load_records("weather"),
                *self.data_provider.load_records("umpires"),
                *self.data_provider.load_records("park_factors"),
                *weak_spot_rows,
                *hr_matchup_rows,
            ]
        )
        games: list[GameIntake] = []
        for game_id in game_ids:
            environment = environments.get(game_id)
            away_team, home_team = _teams_for_game(game_id, lineups, pitchers, environment)
            games.append(
                GameIntake(
                    game_id=game_id,
                    date=environment.date if environment else "",
                    away_team=TeamIntake(
                        team=away_team,
                        batters=lineups.get(game_id, {}).get(away_team, []),
                        starting_pitcher=pitchers.get(game_id, {}).get(away_team),
                    ),
                    home_team=TeamIntake(
                        team=home_team,
                        batters=lineups.get(game_id, {}).get(home_team, []),
                        starting_pitcher=pitchers.get(game_id, {}).get(home_team),
                    ),
                    environment=environment,
                    umpire=environment.umpire if environment else self.load_umpires().get(game_id),
                    weak_spots=weak_spots.get(game_id, []),
                    hr_matchups=hr_matchups.get(game_id, []),
                    original_game_id=_preferred_original_game_id(game_id, original_game_ids),
                )
            )
        return games

    def load_daily_slate(self, slate_date: str | None = None) -> DailySlate:
        games = self.load_game_data()
        watchlist = self.load_watchlist()
        inferred_date = slate_date or next((game.date for game in games if game.date), "")
        unmatched_game_ids = self._unmatched_game_ids(games)
        return DailySlate(
            date=inferred_date,
            games=games,
            watchlist=WatchlistImport(games=games, batters=watchlist.batters, metadata=watchlist.metadata),
            metadata={
                "source": self.data_provider.__class__.__name__,
                "unmatched_game_ids": json.dumps(unmatched_game_ids, sort_keys=True),
            },
        )

    def _unmatched_game_ids(self, games: Sequence[GameIntake]) -> dict[str, list[str]]:
        loaded_game_ids = {game.game_id for game in games}
        unmatched: dict[str, list[str]] = {}
        for dataset in [
            "watchlist",
            "lineups",
            "pitchers",
            "weather",
            "umpires",
            "park_factors",
            "weak_spots",
            "hr_matchups",
        ]:
            originals: list[str] = []
            for row in self.data_provider.load_records(dataset):
                normalized, original = _game_id_from_record(row)
                if normalized and normalized not in loaded_game_ids and original not in originals:
                    originals.append(original)
            if originals:
                unmatched[dataset] = originals
        return unmatched


def load_watchlist(provider: DataProvider | WatchlistProvider) -> WatchlistImport:
    if isinstance(provider, WatchlistProvider):
        return provider.load_watchlist()
    return MLBDataConnector(provider).load_watchlist()


def load_game_data(provider: DataProvider | MLBDataConnector) -> list[GameIntake]:
    if isinstance(provider, MLBDataConnector):
        return provider.load_game_data()
    return MLBDataConnector(provider).load_game_data()


def load_daily_slate(provider: DataProvider | MLBDataConnector, slate_date: str | None = None) -> DailySlate:
    if isinstance(provider, MLBDataConnector):
        return provider.load_daily_slate(slate_date)
    return MLBDataConnector(provider).load_daily_slate(slate_date)


def _clean_record(row: Mapping[str, Any]) -> Record:
    return {str(key).strip(): value.strip() if isinstance(value, str) else value for key, value in row.items() if key is not None}


def _records_from_json(payload: Any, dataset: str) -> list[Record]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        nested = payload.get(dataset, payload.get(_plural(dataset)))
        if nested is not None:
            return _records_from_json(nested, dataset)
        return [_clean_record(payload)]
    if isinstance(payload, list):
        return [_clean_record(item) for item in payload if isinstance(item, Mapping)]
    return []


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _plural(dataset: str) -> str:
    if dataset.endswith("s"):
        return dataset
    return f"{dataset}s"


def normalize_game_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = raw.lower().replace("_", "-").replace(" ", "")
    if "@" in compact:
        away, home = compact.split("@", 1)
        if _is_team_code(away) and _is_team_code(home):
            return f"{away}-{home}-1"
    parts = [part for part in compact.split("-") if part]
    if len(parts) >= 5 and parts[-3].isdigit() and parts[-2].isdigit() and parts[-1].isdigit():
        prefix = parts[:-3]
        if len(prefix) == 3 and prefix[1] == "at" and _is_team_code(prefix[0]) and _is_team_code(prefix[2]):
            return f"{prefix[0]}-{prefix[2]}-1"
        if len(prefix) == 2 and _is_team_code(prefix[0]) and _is_team_code(prefix[1]):
            return f"{prefix[0]}-{prefix[1]}-1"
    if len(parts) == 3 and parts[1] == "at" and _is_team_code(parts[0]) and _is_team_code(parts[2]):
        return f"{parts[0]}-{parts[2]}-1"
    if len(parts) == 3 and _is_team_code(parts[0]) and _is_team_code(parts[1]) and parts[2].isdigit():
        return f"{parts[0]}-{parts[1]}-{int(parts[2])}"
    if len(parts) == 2 and _is_team_code(parts[0]) and _is_team_code(parts[1]):
        return f"{parts[0]}-{parts[1]}-1"
    if len(parts) == 1:
        return parts[0]
    return compact


def _game_id_from_record(row: Mapping[str, Any]) -> tuple[str, str]:
    original = str(_value(row, "game_id", "game", default="")).strip()
    return normalize_game_id(original), original


def _is_team_code(value: str) -> bool:
    return bool(_TEAM_CODE.match(value))


def _original_game_ids_by_normalized(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    originals: dict[str, list[str]] = {}
    for row in rows:
        normalized, original = _game_id_from_record(row)
        if normalized and original and original not in originals.setdefault(normalized, []):
            originals[normalized].append(original)
    return originals


def _preferred_original_game_id(game_id: str, originals: Mapping[str, Sequence[str]]) -> str:
    values = originals.get(game_id, [])
    for value in values:
        if value and value != game_id:
            return value
    return values[0] if values else game_id


def _value(row: Mapping[str, Any], *names: str, default: Any = "") -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            value = lowered[name.lower()]
            if value is not None and value != "":
                return value
    return default


def _float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "confirmed"}


def _handedness(value: Any) -> Handedness:
    raw = str(value or "").strip().upper()
    if raw in {"L", "LEFT", "LEFTY"}:
        return Handedness.L
    if raw in {"R", "RIGHT", "RIGHTY"}:
        return Handedness.R
    if raw in {"S", "SWITCH"}:
        return Handedness.S
    return Handedness.UNKNOWN


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("|", ",").replace(";", ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _batter_from_record(row: Mapping[str, Any], *, confirmed: bool, source: str = "watchlist") -> BatterIntake:
    slot = _int(_value(row, "lineup_slot", "slot", "batting_order", default=None))
    return BatterIntake(
        name=str(_value(row, "name", "batter", "batter_name", default="")).strip(),
        team=str(_value(row, "team", default="")).strip(),
        lineup_slot=slot,
        bats=_handedness(_value(row, "bats", "handedness", default="UNKNOWN")),
        hr_pct=_float(_value(row, "hr_pct", "hr_percent", "hr_probability", default=0.0)),
        pitch_mix_score=_float(_value(row, "pitch_mix_score", "pitch_fit", default=0.0)),
        projected_ab=_int(_value(row, "projected_ab", "ab", default=4)) or 4,
        projected_hits=_float(_value(row, "projected_hits", "hits", default=0.0)),
        fair_odds=_int(_value(row, "fair_odds", default=None)),
        book_odds=_int(_value(row, "book_odds", "odds", default=None)),
        tags=_tags(_value(row, "tags", default="")),
        confirmed=confirmed or _bool(_value(row, "confirmed", default=False)),
        source=source,
    )


def _weak_spots_by_game(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[PitcherWeakSpot]]:
    grouped: dict[str, list[PitcherWeakSpot]] = {}
    for row in rows:
        game_id, original_game_id = _game_id_from_record(row)
        if not game_id:
            continue
        grouped.setdefault(game_id, []).append(
            PitcherWeakSpot(
                pitcher_name=str(_value(row, "pitcher_name", "pitcher", default="")).strip(),
                pitch=str(_value(row, "pitch", "pitch_type", default="")).strip(),
                zone=str(_value(row, "zone", default="")).strip() or None,
                weakness_score=_float(_value(row, "weakness_score", "score", default=0.0)),
                notes=str(_value(row, "notes", default="")).strip(),
                original_game_id=original_game_id,
            )
        )
    return grouped


def _hr_matchups_by_game(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[HRMatchup]]:
    grouped: dict[str, list[HRMatchup]] = {}
    for row in rows:
        game_id, original_game_id = _game_id_from_record(row)
        if not game_id:
            continue
        grouped.setdefault(game_id, []).append(
            HRMatchup(
                batter_name=str(_value(row, "batter_name", "batter", default="")).strip(),
                pitcher_name=str(_value(row, "pitcher_name", "pitcher", default="")).strip(),
                pitch=str(_value(row, "pitch", "pitch_type", default="")).strip(),
                matchup_score=_float(_value(row, "matchup_score", "score", default=0.0)),
                exit_velo=_optional_float(_value(row, "exit_velo", "exit_velocity", default=None)),
                angle=_optional_float(_value(row, "angle", "launch_angle", default=None)),
                distance=_optional_float(_value(row, "distance", default=None)),
                notes=str(_value(row, "notes", default="")).strip(),
                original_game_id=original_game_id,
            )
        )
    return grouped


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return _float(value)


def _teams_for_game(
    game_id: str,
    lineups: Mapping[str, Mapping[str, Sequence[BatterIntake]]],
    pitchers: Mapping[str, Mapping[str, PitcherIntake]],
    environment: GameEnvironment | None,
) -> tuple[str, str]:
    if environment and environment.away_team and environment.home_team:
        return environment.away_team, environment.home_team
    teams = list(lineups.get(game_id, {}).keys()) or list(pitchers.get(game_id, {}).keys())
    away = teams[0] if teams else ""
    home = teams[1] if len(teams) > 1 else ""
    return away, home
