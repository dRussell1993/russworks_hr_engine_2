from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from russworks.models import Handedness
from .batter import BatterIntake


@dataclass(frozen=True)
class PitcherIntake:
    name: str
    team: str
    throws: Handedness = Handedness.UNKNOWN
    tags: List[str] = field(default_factory=list)
    projected_ip: float = 0.0
    projected_hits: float = 0.0
    projected_hr: float = 0.0
    projected_bb: float = 0.0
    projected_er: float = 0.0
    projected_outs: float = 0.0
    confirmed: bool = False


@dataclass(frozen=True)
class TeamIntake:
    team: str
    batters: List[BatterIntake] = field(default_factory=list)
    starting_pitcher: Optional[PitcherIntake] = None

    @property
    def confirmed_batters(self) -> List[BatterIntake]:
        return [batter for batter in self.batters if batter.confirmed]
