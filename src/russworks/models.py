from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Handedness(str, Enum):
    L = "L"
    R = "R"
    S = "S"
    UNKNOWN = "UNKNOWN"


class RussTier(str, Enum):
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"
    NO = "No"


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


@dataclass
class Pitcher:
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


@dataclass
class Batter:
    name: str
    team: str
    bats: Handedness = Handedness.UNKNOWN
    lineup_slot: int = 0
    hr_pct: float = 0.0
    pitch_mix_score: float = 0.0
    projected_ab: int = 4
    projected_hits: float = 0.0
    fair_odds: Optional[int] = None
    book_odds: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    confirmed: bool = True


@dataclass
class PitcherWeakSpot:
    pitcher_name: str
    pitch: str
    zone: Optional[str] = None
    weakness_score: float = 0.0
    notes: str = ""


@dataclass
class HRMatchup:
    batter_name: str
    pitcher_name: str
    pitch: str
    matchup_score: float = 0.0
    exit_velo: Optional[float] = None
    angle: Optional[float] = None
    distance: Optional[float] = None
    notes: str = ""


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


@dataclass
class BatterScore:
    batter: Batter
    opponent_pitcher: Pitcher
    lpas: float
    tag_component: float
    cps_component: float
    ypi: float
    catcher_power: float
    veteran_bounce: float
    chaos_cluster: float
    pitcher_collision: float
    environment: float
    final_score: float
    tier: RussTier
    board: str
    notes: List[str] = field(default_factory=list)


@dataclass
class TeamClusterScore:
    team: str
    tag_score: float
    tag_grade: str
    cps_score: float
    cps_grade: str
    cluster_score: float
    core_batters: List[str]
    notes: List[str] = field(default_factory=list)


@dataclass
class Slip:
    name: str
    batters: List[str]
    grade: str
    slip_type: str
    rationale: str


@dataclass
class PostMortemEntry:
    date: str
    batter: str
    team: str
    result: str
    formula_status: str
    step3_score: Optional[float] = None
    cluster_score: Optional[float] = None
    pitch: Optional[str] = None
    pitcher: Optional[str] = None
    notes: str = ""
