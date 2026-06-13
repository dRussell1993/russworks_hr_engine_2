from __future__ import annotations

from typing import Any, Iterable, Mapping

from russworks.providers.mlb_stats import LiveProviderBase, ProviderResult


class BallparkProvider(LiveProviderBase):
    """Ballpark provider for HR park factors.

    Configure with `RUSSWORKS_BALLPARK_BASE_URL`; optionally set
    `RUSSWORKS_BALLPARK_API_KEY`.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="ballpark",
            base_url_env="RUSSWORKS_BALLPARK_BASE_URL",
            api_key_env="RUSSWORKS_BALLPARK_API_KEY",
            **kwargs,
        )

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        if dataset != "park_factors":
            return super().fetch_dataset(dataset, date)
        result = self._fetch_json("park_factors", {"date": date})
        return ProviderResult(
            provider=self.name,
            dataset=dataset,
            records=_normalize_park_factors(result.records),
            success=result.success,
            errors=result.errors,
            metadata=result.metadata,
        )

    def fetch_ballparks(self, date: str) -> ProviderResult:
        return self.fetch_dataset("park_factors", date)


def _normalize_park_factors(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for record in records:
        normalized.append(
            {
                "game_id": _first(record, "game_id", "gamePk", "game"),
                "park": _first(record, "park", "park_name", "venue"),
                "park_hr_factor": _first(record, "park_hr_factor", "hr_park_factor", default=0.0),
                "left_field_carry": _first(record, "left_field_carry", default=0.0),
                "center_field_carry": _first(record, "center_field_carry", default=0.0),
                "right_field_carry": _first(record, "right_field_carry", default=0.0),
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
