from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


class IntegritySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class IntegrityAlert:
    severity: IntegritySeverity
    category: str
    message: str
    location: str = ""
    provider: str = ""
    field: str = ""
    value: Any = None


@dataclass(frozen=True)
class DataIntegrityResult:
    dataset: str
    checked_records: int = 0
    alerts: list[IntegrityAlert] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not any(alert.severity in {IntegritySeverity.ERROR, IntegritySeverity.CRITICAL} for alert in self.alerts)

    @property
    def alert_count(self) -> int:
        return len(self.alerts)


@dataclass(frozen=True)
class ProviderIntegrityResult:
    provider: str
    dataset: str
    checked_records: int = 0
    success: bool = True
    alerts: list[IntegrityAlert] = field(default_factory=list)

    @property
    def alert_count(self) -> int:
        return len(self.alerts)


@dataclass(frozen=True)
class IntegrityReport:
    generated_at: str
    date: str = ""
    data_results: list[DataIntegrityResult] = field(default_factory=list)
    provider_results: list[ProviderIntegrityResult] = field(default_factory=list)
    alerts: list[IntegrityAlert] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not any(alert.severity in {IntegritySeverity.ERROR, IntegritySeverity.CRITICAL} for alert in self.alerts)

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in IntegritySeverity}
        for alert in self.alerts:
            counts[alert.severity.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        payload = _json_ready(asdict(self))
        payload["success"] = self.success
        payload["severity_counts"] = self.severity_counts
        return payload

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
