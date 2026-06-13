from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any


@dataclass(frozen=True)
class ExplanationFactor:
    name: str
    value: str | int | float | bool
    impact: str
    summary: str
    source: str


@dataclass(frozen=True)
class BatterExplanation:
    batter: str
    team: str
    summary: str
    factors: list[ExplanationFactor] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class SlipExplanation:
    slip_name: str
    slip_type: str
    summary: str
    batter_selection_reasons: dict[str, list[ExplanationFactor]] = field(default_factory=dict)
    archetype_factors: list[ExplanationFactor] = field(default_factory=list)
    validation_factors: list[ExplanationFactor] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TeamExplanation:
    team: str
    rank: int
    summary: str
    ranking_factors: list[ExplanationFactor] = field(default_factory=list)
    cluster_drivers: list[ExplanationFactor] = field(default_factory=list)
    offensive_concentration: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


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
