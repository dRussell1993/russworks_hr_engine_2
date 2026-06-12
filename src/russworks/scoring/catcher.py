from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class CatcherProfile:
    batter_name: str
    primary_position: str = ""
    games_caught: int = 0
    lineup_slot: int | None = None
    recent_hr_trend: float = 0.0
    barrel_rate: float = 0.0
    hard_hit_rate: float = 0.0
    exit_velocity: float = 0.0
    fly_ball_profile: float = 0.0
    pull_profile: float = 0.0
    team_tag: float = 0.0
    team_cps: float = 0.0


@dataclass(frozen=True)
class CatcherPowerResult:
    catcher_power_score: float
    confidence: float
    grade: str
    is_catcher: bool
    above_average_hr_upside: bool
    strong_cluster_context: bool
    premium_lineup_slot: bool
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class CatcherPowerEngine:
    def score_profile(self, profile: CatcherProfile) -> CatcherPowerResult:
        is_catcher = _is_catcher(profile)
        confidence = _confidence(profile)
        if not is_catcher:
            return CatcherPowerResult(
                catcher_power_score=0.0,
                confidence=confidence,
                grade="Weak",
                is_catcher=False,
                above_average_hr_upside=False,
                strong_cluster_context=False,
                premium_lineup_slot=False,
                components={"not_catcher": 0.0},
                notes=["Catcher Power does not apply to non-catchers"],
            )

        games_component = _clamp(profile.games_caught / 10.0, 0.0, 8.0)
        lineup_component = _lineup_component(profile.lineup_slot)
        hr_trend_component = _clamp(profile.recent_hr_trend * 4.0, -8.0, 16.0)
        barrel_component = _clamp((profile.barrel_rate - 6.0) * 2.0, -10.0, 18.0)
        hard_hit_component = _clamp((profile.hard_hit_rate - 36.0) * 0.65, -10.0, 16.0)
        exit_velocity_component = _clamp((profile.exit_velocity - 88.0) * 2.0, -8.0, 14.0)
        fly_ball_component = _clamp((profile.fly_ball_profile - 32.0) * 0.45, -8.0, 12.0)
        pull_component = _clamp((profile.pull_profile - 38.0) * 0.35, -6.0, 10.0)
        cluster_component = _cluster_component(profile.team_tag, profile.team_cps)
        unsupported_catcher_component = -10.0 if not _has_power_skills(profile) else 0.0

        components = {
            "games_caught": round(games_component, 2),
            "lineup_slot": round(lineup_component, 2),
            "recent_hr_trend": round(hr_trend_component, 2),
            "barrel_rate": round(barrel_component, 2),
            "hard_hit_rate": round(hard_hit_component, 2),
            "exit_velocity": round(exit_velocity_component, 2),
            "fly_ball_profile": round(fly_ball_component, 2),
            "pull_profile": round(pull_component, 2),
            "team_cluster": round(cluster_component, 2),
            "unsupported_catcher": round(unsupported_catcher_component, 2),
        }
        score = round(_clamp(25.0 + sum(components.values()), 0.0, 100.0), 2)
        above_average = _has_power_skills(profile) and score >= 58.0
        strong_cluster = profile.team_tag >= 82.0 and profile.team_cps >= 82.0
        premium_slot = profile.lineup_slot in {1, 2, 3, 4, 5}
        return CatcherPowerResult(
            catcher_power_score=score,
            confidence=confidence,
            grade=_grade(score, confidence),
            is_catcher=True,
            above_average_hr_upside=above_average,
            strong_cluster_context=strong_cluster,
            premium_lineup_slot=premium_slot,
            components=components,
            notes=_notes(above_average, strong_cluster, premium_slot, unsupported_catcher_component < 0),
        )


def calculate_catcher_power_score(profile: CatcherProfile) -> CatcherPowerResult:
    return CatcherPowerEngine().score_profile(profile)


def _is_catcher(profile: CatcherProfile) -> bool:
    position = profile.primary_position.strip().lower()
    return position in {"c", "catcher"} or "catcher" in position


def _has_power_skills(profile: CatcherProfile) -> bool:
    return (
        profile.barrel_rate >= 8.0
        and profile.hard_hit_rate >= 40.0
        and profile.exit_velocity >= 89.0
    ) or (profile.recent_hr_trend >= 1.5 and profile.barrel_rate >= 7.0)


def _lineup_component(slot: int | None) -> float:
    if slot is None or slot <= 0:
        return -5.0
    if slot == 4:
        return 12.0
    if slot == 3:
        return 10.0
    if slot in {1, 2, 5}:
        return 8.0
    if slot == 6:
        return 1.0
    if slot == 7:
        return -2.0
    return -5.0


def _cluster_component(tag: float, cps: float) -> float:
    if tag >= 88.0 and cps >= 88.0:
        return 12.0
    if tag >= 82.0 and cps >= 82.0:
        return 8.0
    if tag >= 75.0 or cps >= 75.0:
        return 4.0
    if tag < 60.0 and cps < 60.0:
        return -6.0
    return 0.0


def _confidence(profile: CatcherProfile) -> float:
    available = 0
    available += 1 if profile.primary_position else 0
    available += 1 if profile.games_caught else 0
    available += 1 if profile.lineup_slot is not None else 0
    available += 1 if profile.recent_hr_trend else 0
    available += 1 if profile.barrel_rate else 0
    available += 1 if profile.hard_hit_rate else 0
    available += 1 if profile.exit_velocity else 0
    available += 1 if profile.fly_ball_profile else 0
    available += 1 if profile.pull_profile else 0
    available += 1 if profile.team_tag else 0
    available += 1 if profile.team_cps else 0
    return round(_clamp(available / 11.0, 0.15, 1.0), 2)


def _grade(score: float, confidence: float) -> str:
    adjusted = score * (0.85 + confidence * 0.15)
    if adjusted >= 82.0:
        return "Elite"
    if adjusted >= 70.0:
        return "Strong"
    if adjusted >= 58.0:
        return "Moderate"
    if adjusted >= 42.0:
        return "Neutral"
    return "Weak"


def _notes(
    above_average: bool,
    strong_cluster: bool,
    premium_slot: bool,
    unsupported: bool,
) -> List[str]:
    notes: List[str] = []
    if above_average:
        notes.append("above-average catcher HR upside")
    if strong_cluster:
        notes.append("strong TAG/CPS catcher context")
    if premium_slot:
        notes.append("premium catcher lineup slot")
    if unsupported:
        notes.append("catcher status alone is not enough")
    if not notes:
        notes.append("no active Catcher Power boost")
    return notes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
