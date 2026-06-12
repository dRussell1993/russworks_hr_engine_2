from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from russworks.models import Handedness


@dataclass(frozen=True)
class BatterIntake:
    name: str
    team: str
    lineup_slot: Optional[int] = None
    bats: Handedness = Handedness.UNKNOWN
    hr_pct: float = 0.0
    pitch_mix_score: float = 0.0
    projected_ab: int = 4
    projected_hits: float = 0.0
    fair_odds: Optional[int] = None
    book_odds: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    confirmed: bool = False
    source: str = "watchlist"

    @property
    def requires_review(self) -> bool:
        return bool(self.name and self.team)
