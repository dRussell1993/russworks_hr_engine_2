from __future__ import annotations

from typing import Any

from russworks.providers.mlb_stats import LiveProviderBase, ProviderResult


class BaseballSavantProvider(LiveProviderBase):
    """Baseball Savant-style provider for matchup enrichment.

    Configure with `RUSSWORKS_BASEBALL_SAVANT_BASE_URL`; optionally set
    `RUSSWORKS_BASEBALL_SAVANT_API_KEY`.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="baseball_savant",
            base_url_env="RUSSWORKS_BASEBALL_SAVANT_BASE_URL",
            api_key_env="RUSSWORKS_BASEBALL_SAVANT_API_KEY",
            **kwargs,
        )

    def fetch_dataset(self, dataset: str, date: str) -> ProviderResult:
        endpoints = {
            "weak_spots": "weak_spots",
            "hr_matchups": "hr_matchups",
        }
        endpoint = endpoints.get(dataset)
        if endpoint is None:
            return super().fetch_dataset(dataset, date)
        result = self._fetch_json(endpoint, {"date": date})
        return ProviderResult(
            provider=self.name,
            dataset=dataset,
            records=result.records,
            success=result.success,
            errors=result.errors,
            metadata=result.metadata,
        )

    def fetch_weak_spots(self, date: str) -> ProviderResult:
        return self.fetch_dataset("weak_spots", date)

    def fetch_hr_matchups(self, date: str) -> ProviderResult:
        return self.fetch_dataset("hr_matchups", date)
