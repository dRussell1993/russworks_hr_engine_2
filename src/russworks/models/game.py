from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .batter import Batter, HRMatchup, PitcherWeakSpot
from .team import Pitcher


@dataclass
class Umpire:
    name: str
    zone_type: str = "Neutral"
    called_strike_rate: float = 0.0
    accuracy: float = 0.0
    consistency: float = 0.0
    run_lean: float = 0.0


@dataclass
class GameEnvironment:
    game_id: str
    date: str
    away_team: str
    home_team: str
    park: str
    temperature_f: float = 70.0
    wind_mph: float = 0.0
    wind_direction: str = ""
    humidity_pct: float = 0.0
    roof: str = "open"
    weather_hr_pct: float = 0.0
    weather_distance_ft: float = 0.0
    park_hr_factor: float = 0.0
    umpire: Optional[Umpire] = None
    original_game_id: str = ""


@dataclass
class Game:
    game_id: str
    environment: GameEnvironment
    away_pitcher: Pitcher
    home_pitcher: Pitcher
    batters: List[Batter]
    weak_spots: List[PitcherWeakSpot] = field(default_factory=list)
    hr_matchups: List[HRMatchup] = field(default_factory=list)

    def batters_for_team(self, team: str) -> List[Batter]:
        return sorted([b for b in self.batters if b.team == team], key=lambda b: b.lineup_slot)
