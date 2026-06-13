from __future__ import annotations

from typing import Any, Iterable, Mapping

from russworks.providers.mlb_stats import LiveProviderBase, ProviderResult


class WeatherProvider(LiveProviderBase):
    """Weather provider for daily game environments.

    Configure with `RUSSWORKS_WEATHER_BASE_URL`; optionally set
    `RUSSWORKS_WEATHER_API_KEY`.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="weather",
            base_url_env="RUSSWORKS_WEATHER_BASE_URL",
            api_key_env="RUSSWORKS_WEATHER_API_KEY",
            **kwargs,
        )

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        if dataset != "weather":
            return super().fetch_dataset(dataset, date)
        result = self._fetch_json("weather", {"date": date})
        return ProviderResult(
            provider=self.name,
            dataset=dataset,
            records=_normalize_weather(result.records),
            success=result.success,
            errors=result.errors,
            metadata=result.metadata,
        )

    def fetch_weather(self, date: str) -> ProviderResult:
        return self.fetch_dataset("weather", date)


def _normalize_weather(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for record in records:
        normalized.append(
            {
                "game_id": _first(record, "game_id", "gamePk", "game"),
                "date": _first(record, "date"),
                "away_team": _first(record, "away_team", "away"),
                "home_team": _first(record, "home_team", "home"),
                "park": _first(record, "park", "venue", "ballpark"),
                "temperature_f": _first(record, "temperature_f", "temperature", "temp_f", default=70.0),
                "wind_mph": _first(record, "wind_mph", "wind_speed", default=0.0),
                "wind_direction": _first(record, "wind_direction", default=""),
                "humidity_pct": _first(record, "humidity_pct", "humidity", default=0.0),
                "roof": _first(record, "roof", "roof_status", default="open"),
                "weather_hr_pct": _first(record, "weather_hr_pct", "weather_boost", default=0.0),
                "weather_distance_ft": _first(record, "weather_distance_ft", "distance_boost", default=0.0),
                "park_hr_factor": _first(record, "park_hr_factor", "hr_park_factor", default=0.0),
            }
        )
    return normalized


def _first(record: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        if key in record and record[key] not in {None, ""}:
            return record[key]
        lowered_key = key.lower()
        if lowered_key in lowered and lowered[lowered_key] not in {None, ""}:
            return lowered[lowered_key]
    return default
