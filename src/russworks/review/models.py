from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from russworks.models import RussTier


@dataclass(frozen=True)
class BatterReview:
    batter_name: str
    team: str
    opponent: str
    lineup_slot: int
    hr_pct: float
    lstm_score: float
    tag_contribution: float
    cps_contribution: float
    pvs_contribution: float
    environment_score: float
    umpire_score: float
    ypi_flag: bool
    catcher_power_flag: bool
    veteran_bounce_flag: bool
    non_superstar_core_flag: bool
    weak_spot_collision_flag: bool
    final_russ_score: float
    russ_tier: RussTier
    notes: List[str] = field(default_factory=list)
    weak_spot_collision_score: float = 0.0
    weak_spot_collision_confidence: float = 0.0
    weak_spot_collision_grade: str = "D"
    ypi_score: float = 0.0
    ypi_confidence: float = 0.0
    ypi_grade: str = "Weak"
    veteran_bounce_score: float = 0.0
    veteran_bounce_confidence: float = 0.0
    veteran_bounce_grade: str = "Weak"
    catcher_power_score: float = 0.0
    catcher_power_confidence: float = 0.0
    catcher_power_grade: str = "Weak"
    pitch_mix_matchup_score: float = 0.0
    pitch_mix_matchup_confidence: float = 0.0
    pitch_mix_matchup_grade: str = "Weak"
    bullpen_exposure_score: float = 0.0
    bullpen_exposure_confidence: float = 0.0
    bullpen_exposure_grade: str = "Weak"


@dataclass(frozen=True)
class BatterReviewResult:
    total_batters: int
    reviewed_batters: int
    reviews: List[BatterReview] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    skipped_batters: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and self.reviewed_batters == self.total_batters
