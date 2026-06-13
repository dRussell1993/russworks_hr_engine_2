from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class SlipLeg:
    batter: str
    team: str
    tag: str
    cps: str
    russ_score: float
    slip_role: str
    justification: str
    confidence_score: float = 0.0
    confidence_grade: str = "Very Low"
    confidence_reasoning: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Slip:
    name: str
    slip_type: str
    legs: List[SlipLeg]
    justification: str
    metadata: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.0
    confidence_grade: str = "Very Low"
    confidence_reasoning: List[str] = field(default_factory=list)

    @property
    def batters(self) -> List[str]:
        return [leg.batter for leg in self.legs]


@dataclass(frozen=True)
class SlipPortfolio:
    core_slips: List[Slip] = field(default_factory=list)
    non_superstar_core_slips: List[Slip] = field(default_factory=list)
    balanced_slips: List[Slip] = field(default_factory=list)
    chaos_slips: List[Slip] = field(default_factory=list)
    contrarian_slips: List[Slip] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    @property
    def all_slips(self) -> List[Slip]:
        return [
            *self.core_slips,
            *self.non_superstar_core_slips,
            *self.balanced_slips,
            *self.chaos_slips,
            *self.contrarian_slips,
        ]
