from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Handedness(str, Enum):
    L = "L"
    R = "R"
    S = "S"
    UNKNOWN = "UNKNOWN"


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
    original_game_id: str = ""


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
    original_game_id: str = ""
