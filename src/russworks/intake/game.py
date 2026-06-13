from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from russworks.models import GameEnvironment, HRMatchup, PitcherWeakSpot, Umpire
from .team import TeamIntake


@dataclass(frozen=True)
class GameIntake:
    game_id: str
    date: str
    away_team: TeamIntake
    home_team: TeamIntake
    environment: Optional[GameEnvironment] = None
    umpire: Optional[Umpire] = None
    weak_spots: List[PitcherWeakSpot] = field(default_factory=list)
    hr_matchups: List[HRMatchup] = field(default_factory=list)
    original_game_id: str = ""

    @property
    def teams(self) -> List[TeamIntake]:
        return [self.away_team, self.home_team]
