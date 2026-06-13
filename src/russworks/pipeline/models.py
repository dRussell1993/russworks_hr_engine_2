from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
import json
from typing import Any

from russworks.cluster import ClusterRanking
from russworks.data import DailySlate
from russworks.diversification import DiversificationResult
from russworks.integrity import IntegrityReport
from russworks.portfolio import PortfolioProfile
from russworks.reports import FullRussWorksReport
from russworks.review import BatterReviewResult
from russworks.slips import SlipPortfolio


@dataclass(frozen=True)
class DailyRunRequest:
    date: str
    data_root: str = "data/daily"
    output_root: str = "data/outputs"
    provider_mode: str = "csv"
    config_path: str = "config/russworks_config.yaml"


@dataclass(frozen=True)
class DailyRunResult:
    request: DailyRunRequest
    success: bool
    validation_status: str
    missing_data: dict[str, list[str]] = field(default_factory=dict)
    total_batters_reviewed: int = 0
    output_dir: str = ""
    report_json_path: str = ""
    integrity_report_path: str = ""
    portfolio_report_path: str = ""
    diversification_report_path: str = ""
    slate: DailySlate | None = None
    integrity_report: IntegrityReport | None = None
    portfolio_report: PortfolioProfile | None = None
    diversification_report: DiversificationResult | None = None
    step3_result: BatterReviewResult | None = None
    step4_result: ClusterRanking | None = None
    step5_result: SlipPortfolio | None = None
    full_report: FullRussWorksReport | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


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
