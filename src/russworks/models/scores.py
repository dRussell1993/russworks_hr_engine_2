from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .batter import Batter
from .team import Pitcher


class RussTier(str, Enum):
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"
    NO = "No"


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
