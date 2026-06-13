from __future__ import annotations

import json
import os
import time
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from russworks.data import DailySlate, DataProvider, MLBDataConnector


Record = dict[str, Any]


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    dataset: str
    records: list[Record] = field(default_factory=list)
    success: bool = True
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    status: str
    checked_at: str
    rate_limited: bool = False
    retry_count: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


class Provider(ABC):
    name = "provider"

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            dataset=dataset,
            records=[],
            success=False,
            errors=[f"{self.name} does not support dataset: {dataset}"],
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status="unknown", checked_at=_now())


class LiveProviderBase(Provider):
    def __init__(
        self,
        *,
        name: str,
        base_url_env: str,
        api_key_env: str | None = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        min_interval_seconds: float = 0.25,
        requester: Callable[[str, Mapping[str, str], float], Any] | None = None,
    ) -> None:
        self.name = name
        self.base_url_env = base_url_env
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.min_interval_seconds = min_interval_seconds
        self._requester = requester or _default_requester
        self._last_request_at = 0.0
        self._last_health = ProviderHealth(provider=name, status="not_checked", checked_at=_now())

    @property
    def configured(self) -> bool:
        return bool(os.getenv(self.base_url_env))

    def health(self) -> ProviderHealth:
        if not self.configured:
            self._last_health = ProviderHealth(
                provider=self.name,
                status="not_configured",
                checked_at=_now(),
                errors=[f"Missing base URL environment variable: {self.base_url_env}"],
            )
        return self._last_health

    def _fetch_json(self, path: str, query: Mapping[str, str]) -> ProviderResult:
        if not self.configured:
            result = ProviderResult(
                provider=self.name,
                dataset=path,
                success=False,
                errors=[f"Provider not configured. Set {self.base_url_env} to enable live ingestion."],
            )
            self._last_health = ProviderHealth(provider=self.name, status="not_configured", checked_at=_now(), errors=result.errors)
            return result

        base_url = os.getenv(self.base_url_env, "").rstrip("/")
        url = _build_url(f"{base_url}/{path.lstrip('/')}", query)
        headers = {"Accept": "application/json"}
        if self.api_key_env and os.getenv(self.api_key_env):
            headers["Authorization"] = f"Bearer {os.getenv(self.api_key_env)}"

        errors: list[str] = []
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            try:
                payload = self._requester(url, headers, self.timeout_seconds)
                records = _records(payload)
                self._last_health = ProviderHealth(
                    provider=self.name,
                    status="ok",
                    checked_at=_now(),
                    retry_count=attempt,
                    metadata={"url": _redact_url(url)},
                )
                return ProviderResult(
                    provider=self.name,
                    dataset=path,
                    records=records,
                    metadata={"url": _redact_url(url), "attempts": str(attempt + 1)},
                )
            except RateLimitError as exc:
                errors.append(str(exc))
                self._last_health = ProviderHealth(
                    provider=self.name,
                    status="rate_limited",
                    checked_at=_now(),
                    rate_limited=True,
                    retry_count=attempt,
                    errors=list(errors),
                )
                time.sleep(min(1.0, 0.25 * (attempt + 1)))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append(str(exc))
                time.sleep(min(1.0, 0.20 * (attempt + 1)))

        self._last_health = ProviderHealth(
            provider=self.name,
            status="error",
            checked_at=_now(),
            retry_count=self.max_retries,
            errors=errors,
        )
        return ProviderResult(provider=self.name, dataset=path, records=[], success=False, errors=errors)

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        self._last_request_at = time.monotonic()


class MLBStatsProvider(LiveProviderBase):
    """Live MLB Stats-style provider.

    Configure with `RUSSWORKS_MLB_STATS_BASE_URL`; optionally set
    `RUSSWORKS_MLB_STATS_API_KEY` when a future source requires a key.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="mlb_stats",
            base_url_env="RUSSWORKS_MLB_STATS_BASE_URL",
            api_key_env="RUSSWORKS_MLB_STATS_API_KEY",
            **kwargs,
        )

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        endpoints = {
            "lineups": "lineups",
            "starting_pitchers": "starting_pitchers",
            "probable_pitchers": "probable_pitchers",
            "umpires": "umpires",
        }
        endpoint = endpoints.get(dataset)
        if endpoint is None:
            return super().fetch_dataset(dataset, date)
        result = self._fetch_json(endpoint, {"date": date})
        return ProviderResult(
            provider=self.name,
            dataset=dataset,
            records=_normalize_records(dataset, result.records),
            success=result.success,
            errors=result.errors,
            metadata=result.metadata,
        )

    def fetch_lineups(self, date: str) -> ProviderResult:
        return self.fetch_dataset("lineups", date)

    def fetch_starting_pitchers(self, date: str) -> ProviderResult:
        return self.fetch_dataset("starting_pitchers", date)

    def fetch_probable_pitchers(self, date: str) -> ProviderResult:
        return self.fetch_dataset("probable_pitchers", date)

    def fetch_umpires(self, date: str) -> ProviderResult:
        return self.fetch_dataset("umpires", date)


class InMemoryDataProvider(DataProvider):
    def __init__(self, records_by_dataset: Mapping[str, Iterable[Mapping[str, Any]]]) -> None:
        self.records_by_dataset = {
            dataset: [dict(record) for record in records]
            for dataset, records in records_by_dataset.items()
        }

    def load_records(self, dataset: str) -> list[Record]:
        return list(self.records_by_dataset.get(dataset, []))


class DailySlateProvider:
    def __init__(
        self,
        *,
        providers: Iterable[Provider],
        fallback_provider: DataProvider | None = None,
    ) -> None:
        self.providers = list(providers)
        self.fallback_provider = fallback_provider
        self.results: list[ProviderResult] = []
        self.health_statuses: list[ProviderHealth] = []

    def load_daily_slate(self, date: str) -> DailySlate:
        records_by_dataset: dict[str, list[Record]] = {
            "watchlist": [],
            "lineups": [],
            "pitchers": [],
            "weather": [],
            "umpires": [],
            "park_factors": [],
            "weak_spots": [],
            "hr_matchups": [],
        }
        for dataset in ["lineups", "starting_pitchers", "probable_pitchers", "weather", "umpires", "park_factors"]:
            result = self._fetch_with_fallback(dataset, date)
            self.results.append(result)
            target = "pitchers" if dataset in {"starting_pitchers", "probable_pitchers"} else dataset
            records_by_dataset.setdefault(target, []).extend(result.records)

        if self.fallback_provider is not None:
            for dataset in ["watchlist", "weak_spots", "hr_matchups"]:
                records_by_dataset[dataset].extend(self.fallback_provider.load_records(dataset))

        connector = MLBDataConnector(InMemoryDataProvider(records_by_dataset))
        slate = connector.load_daily_slate(date)
        metadata = dict(slate.metadata)
        metadata.update(self.report_metadata())
        return DailySlate(date=slate.date, games=slate.games, watchlist=slate.watchlist, metadata=metadata)

    def health(self) -> list[ProviderHealth]:
        self.health_statuses = [provider.health() for provider in self.providers]
        return list(self.health_statuses)

    def report_metadata(self) -> dict[str, str]:
        health = self.health()
        metadata = {
            "provider_count": str(len(self.providers)),
            "provider_statuses": ",".join(f"{item.provider}:{item.status}" for item in health),
        }
        failed = [result for result in self.results if not result.success]
        if failed:
            metadata["provider_errors"] = "|".join(f"{result.provider}:{';'.join(result.errors)}" for result in failed)
        return metadata

    def _fetch_with_fallback(self, dataset: str, date: str) -> ProviderResult:
        errors: list[str] = []
        for provider in self.providers:
            result = provider.fetch_dataset(dataset, date)
            if result.success and result.records:
                return result
            if result.errors:
                errors.extend(f"{provider.name}: {error}" for error in result.errors)

        if self.fallback_provider is not None:
            fallback_dataset = "pitchers" if dataset in {"starting_pitchers", "probable_pitchers"} else dataset
            fallback_records = self.fallback_provider.load_records(fallback_dataset)
            if fallback_records:
                return ProviderResult(
                    provider="fallback",
                    dataset=dataset,
                    records=fallback_records,
                    metadata={"source": self.fallback_provider.__class__.__name__},
                )
        return ProviderResult(provider="fallback", dataset=dataset, records=[], success=False, errors=errors or ["no provider data"])


class RateLimitError(RuntimeError):
    pass


def _normalize_records(dataset: str, records: Iterable[Mapping[str, Any]]) -> list[Record]:
    if dataset in {"starting_pitchers", "probable_pitchers"}:
        return [_normalize_pitcher(record, probable=dataset == "probable_pitchers") for record in records]
    if dataset == "lineups":
        return [_normalize_lineup(record) for record in records]
    if dataset == "umpires":
        return [_normalize_umpire(record) for record in records]
    return [dict(record) for record in records]


def _normalize_lineup(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "name": _first(record, "name", "batter", "player_name", "fullName"),
        "team": _first(record, "team", "team_abbrev", "club"),
        "lineup_slot": _first(record, "lineup_slot", "batting_order", "slot"),
        "bats": _first(record, "bats", "handedness"),
        "hr_pct": _first(record, "hr_pct", default=0.0),
        "pitch_mix_score": _first(record, "pitch_mix_score", default=0.0),
        "confirmed": _first(record, "confirmed", default=True),
        "tags": _first(record, "tags", default=""),
    }


def _normalize_pitcher(record: Mapping[str, Any], *, probable: bool) -> Record:
    tags = _first(record, "tags", default="")
    if probable and "probable" not in str(tags).lower():
        tags = f"{tags},probable".strip(",")
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "name": _first(record, "name", "pitcher", "pitcher_name", "fullName"),
        "team": _first(record, "team", "team_abbrev", "club"),
        "throws": _first(record, "throws", "handedness", default="UNKNOWN"),
        "projected_ip": _first(record, "projected_ip", "ip", default=0.0),
        "projected_hits": _first(record, "projected_hits", "hits", default=0.0),
        "projected_hr": _first(record, "projected_hr", "hr", default=0.0),
        "projected_bb": _first(record, "projected_bb", "walks", "bb", default=0.0),
        "confirmed": _first(record, "confirmed", default=not probable),
        "tags": tags,
    }


def _normalize_umpire(record: Mapping[str, Any]) -> Record:
    return {
        "game_id": _first(record, "game_id", "gamePk", "game"),
        "name": _first(record, "name", "umpire", "umpire_name", "fullName"),
        "zone_type": _first(record, "zone_type", default="Neutral"),
        "called_strike_rate": _first(record, "called_strike_rate", default=0.0),
        "accuracy": _first(record, "accuracy", default=0.0),
        "consistency": _first(record, "consistency", default=0.0),
        "run_lean": _first(record, "run_lean", default=0.0),
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


def _records(payload: Any) -> list[Record]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ["records", "data", "items", "lineups", "pitchers", "games"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        return [dict(payload)]
    return []


def _default_requester(url: str, headers: Mapping[str, str], timeout: float) -> Any:
    request = Request(url, headers=dict(headers))
    with urlopen(request, timeout=timeout) as response:
        if response.status == 429:
            raise RateLimitError("Provider rate limit reached.")
        return json.loads(response.read().decode("utf-8"))


def _build_url(url: str, query: Mapping[str, str]) -> str:
    if not query:
        return url
    from urllib.parse import urlencode

    return f"{url}?{urlencode(query)}"


def _redact_url(url: str) -> str:
    return url.split("api_key=")[0] + "api_key=<redacted>" if "api_key=" in url else url


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
