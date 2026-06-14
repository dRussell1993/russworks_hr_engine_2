from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import ActualHomeRunEntry


MLB_STATS_BASE_URL = "https://statsapi.mlb.com/api/v1"
MLB_STATS_FEED_BASE_URL = "https://statsapi.mlb.com/api/v1.1"


class PostMortemNotReady(RuntimeError):
    pass


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
    def __init__(
        self,
        *,
        base_url: str = MLB_STATS_BASE_URL,
        feed_base_url: str = MLB_STATS_FEED_BASE_URL,
        requester: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.feed_base_url = feed_base_url.rstrip("/")
        self.requester = requester or _default_json_requester
        self.timeout_seconds = timeout_seconds

    def fetch_home_runs(self, date: str) -> List[Any]:
        schedule = self._fetch_schedule(date)
        games = _schedule_games(schedule)
        final_games = [game for game in games if _is_final_game(game)]
        if games and len(final_games) != len(games):
            raise PostMortemNotReady("Postmortem not ready.")
        if not games:
            return []

        home_runs: list[dict[str, Any]] = []
        for game in final_games:
            game_id = str(_first_present(game, "gamePk", "game_id", "gameId") or "")
            if not game_id:
                continue
            feed = self._fetch_game_feed(game_id)
            home_runs.extend(_home_run_events(feed, date=date, game_id=game_id))
        return home_runs

    def _fetch_schedule(self, date: str) -> Mapping[str, Any]:
        return _as_response_mapping(
            self.requester(
                _url(f"{self.base_url}/schedule", {"sportId": "1", "date": date}),
                self.timeout_seconds,
            )
        )

    def _fetch_game_feed(self, game_id: str) -> Mapping[str, Any]:
        return _as_response_mapping(
            self.requester(
                f"{self.feed_base_url}/game/{game_id}/feed/live",
                self.timeout_seconds,
            )
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
            "date",
            "game_id",
            "team",
            "opponent",
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
                        "date": entry.metadata.get("date", date),
                        "game_id": entry.metadata.get("game_id", ""),
                        "team": entry.team,
                        "opponent": entry.metadata.get("opponent", ""),
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


def _default_json_requester(url: str, timeout_seconds: float) -> Any:
    with urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _url(url: str, query: Mapping[str, str]) -> str:
    return f"{url}?{urlencode(query)}"


def _as_response_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError("MLB Stats response must be a JSON object.")


def _schedule_games(schedule: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    games: list[Mapping[str, Any]] = []
    for day in schedule.get("dates", []) or []:
        if not isinstance(day, Mapping):
            continue
        for game in day.get("games", []) or []:
            if isinstance(game, Mapping):
                games.append(game)
    return games


def _is_final_game(game: Mapping[str, Any]) -> bool:
    status = game.get("status") if isinstance(game.get("status"), Mapping) else {}
    values = {
        str(status.get("abstractGameState", "")).lower(),
        str(status.get("codedGameState", "")).lower(),
        str(status.get("detailedState", "")).lower(),
        str(status.get("statusCode", "")).lower(),
    }
    return bool(values & {"final", "f", "completed", "game over"})


def _home_run_events(feed: Mapping[str, Any], *, date: str, game_id: str) -> list[dict[str, Any]]:
    plays = _all_plays(feed)
    events = []
    for play in plays:
        if not _is_home_run_play(play):
            continue
        about = _mapping(play.get("about"))
        matchup = _mapping(play.get("matchup"))
        batter = _mapping(matchup.get("batter"))
        pitcher = _mapping(matchup.get("pitcher"))
        team = _batting_team(play, feed)
        opponent = _opponent_for_team(team, feed)
        hit_data = _hit_data(play)
        pitch_data = _pitch_data(play)
        events.append(
            {
                "date": date,
                "game_id": game_id,
                "team": team,
                "batting_team": team,
                "opponent": opponent,
                "batter": _person_name(batter),
                "batter_name": _person_name(batter),
                "pitcher": _person_name(pitcher),
                "pitcher_name": _person_name(pitcher),
                "pitch": _pitch_name(play),
                "inning": _int(about.get("inning"), default=0),
                "exit_velocity": _float(_first_present(hit_data, "launchSpeed", "exitVelocity", "exit_velocity"), default=0.0),
                "distance": _float(_first_present(hit_data, "totalDistance", "distance", "hitDistance"), default=0.0),
                "angle": _float(_first_present(hit_data, "launchAngle", "angle"), default=0.0),
                "pitch_type": str(_first_present(pitch_data, "type", "code") or _pitch_name(play)),
            }
        )
    return events


def _all_plays(feed: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    live_data = _mapping(feed.get("liveData"))
    plays = _mapping(live_data.get("plays"))
    return [play for play in plays.get("allPlays", []) or [] if isinstance(play, Mapping)]


def _is_home_run_play(play: Mapping[str, Any]) -> bool:
    result = _mapping(play.get("result"))
    event = str(_first_present(result, "eventType", "event") or "").strip().lower()
    return event in {"home_run", "home run", "homerun"}


def _batting_team(play: Mapping[str, Any], feed: Mapping[str, Any]) -> str:
    team = _mapping(play.get("team"))
    name = _team_abbreviation(team)
    if name:
        return name
    about = _mapping(play.get("about"))
    half_inning = str(about.get("halfInning", "")).lower()
    teams = _mapping(_mapping(feed.get("gameData")).get("teams"))
    if half_inning == "top":
        return _team_abbreviation(_mapping(teams.get("away")))
    if half_inning == "bottom":
        return _team_abbreviation(_mapping(teams.get("home")))
    return ""


def _opponent_for_team(team: str, feed: Mapping[str, Any]) -> str:
    teams = _mapping(_mapping(feed.get("gameData")).get("teams"))
    away = _team_abbreviation(_mapping(teams.get("away")))
    home = _team_abbreviation(_mapping(teams.get("home")))
    if team == away:
        return home
    if team == home:
        return away
    return home if home else away


def _team_abbreviation(team: Mapping[str, Any]) -> str:
    return str(_first_present(team, "abbreviation", "teamCode", "fileCode", "name") or "").strip()


def _hit_data(play: Mapping[str, Any]) -> Mapping[str, Any]:
    for event in reversed(play.get("playEvents", []) or []):
        if not isinstance(event, Mapping):
            continue
        hit_data = event.get("hitData")
        if isinstance(hit_data, Mapping):
            return hit_data
    return {}


def _pitch_data(play: Mapping[str, Any]) -> Mapping[str, Any]:
    for event in reversed(play.get("playEvents", []) or []):
        if not isinstance(event, Mapping):
            continue
        details = _mapping(event.get("details"))
        pitch_type = details.get("type")
        if isinstance(pitch_type, Mapping):
            return pitch_type
    return {}


def _pitch_name(play: Mapping[str, Any]) -> str:
    pitch_type = _pitch_data(play)
    return str(_first_present(pitch_type, "description", "code") or "Unknown").strip() or "Unknown"


def _person_name(person: Mapping[str, Any]) -> str:
    return str(_first_present(person, "fullName", "name") or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: Any, *, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
