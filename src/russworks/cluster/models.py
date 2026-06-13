from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class TeamClusterReport:
    team: str
    opponent: str
    tag_grade: str
    cps_grade: str
    total_cluster_score: float
    cluster_strength_label: str
    cluster_captain: str
    hidden_cluster_beneficiary: str
    core_bats: List[str] = field(default_factory=list)
    secondary_bats: List[str] = field(default_factory=list)
    non_superstar_cluster_bats: List[str] = field(default_factory=list)
    catcher_power_bats: List[str] = field(default_factory=list)
    ypi_bats: List[str] = field(default_factory=list)
    veteran_bounce_bats: List[str] = field(default_factory=list)
    pitch_mix_matchup_bats: List[str] = field(default_factory=list)
    bullpen_exposure_bats: List[str] = field(default_factory=list)
    park_factor_bats: List[str] = field(default_factory=list)
    batter_count: int = 0
    notes: List[str] = field(default_factory=list)
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
    park_factor_score: float = 0.0
    park_factor_confidence: float = 0.0
    park_factor_grade: str = "Neutral"


@dataclass(frozen=True)
class ClusterRanking:
    total_teams: int
    total_batters: int
    ranked_teams: List[TeamClusterReport] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    missing_batters: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors
