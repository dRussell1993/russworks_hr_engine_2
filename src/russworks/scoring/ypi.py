from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class YPIProfile:
    batter_name: str
    age: int | None = None
    mlb_experience: float = 0.0
    lineup_movement: float = 0.0
    recent_exit_velocity_trend: float = 0.0
    recent_barrel_trend: float = 0.0
    recent_hard_hit_trend: float = 0.0
    hr_trend: float = 0.0
    opportunity_growth: float = 0.0
    playing_time_growth: float = 0.0
    lineup_slot_promotion: float = 0.0
    is_superstar: bool = False


@dataclass(frozen=True)
class YPIResult:
    ypi_score: float
    ypi_confidence: float
    ypi_grade: str
    breakout_candidate: bool
    lineup_promotion_opportunity: bool
    emerging_power_trend: bool
    undervalued_young_hitter: bool
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class YPIEngine:
    def score_profile(self, profile: YPIProfile) -> YPIResult:
        age_component = _age_component(profile.age)
        experience_component = _experience_component(profile.mlb_experience)
        lineup_component = _clamp(profile.lineup_movement * 4.0, -8.0, 12.0)
        exit_velocity_component = _clamp(profile.recent_exit_velocity_trend * 3.0, -10.0, 16.0)
        barrel_component = _clamp(profile.recent_barrel_trend * 4.0, -10.0, 18.0)
        hard_hit_component = _clamp(profile.recent_hard_hit_trend * 2.5, -8.0, 14.0)
        hr_component = _clamp(profile.hr_trend * 4.0, -8.0, 16.0)
        opportunity_component = _clamp(profile.opportunity_growth * 3.0, -6.0, 12.0)
        playing_time_component = _clamp(profile.playing_time_growth * 3.0, -6.0, 12.0)
        promotion_component = _clamp(profile.lineup_slot_promotion * 4.0, -6.0, 14.0)
        non_superstar_component = 5.0 if not profile.is_superstar else -4.0

        components = {
            "age": round(age_component, 2),
            "mlb_experience": round(experience_component, 2),
            "lineup_movement": round(lineup_component, 2),
            "recent_exit_velocity_trend": round(exit_velocity_component, 2),
            "recent_barrel_trend": round(barrel_component, 2),
            "recent_hard_hit_trend": round(hard_hit_component, 2),
            "hr_trend": round(hr_component, 2),
            "opportunity_growth": round(opportunity_component, 2),
            "playing_time_growth": round(playing_time_component, 2),
            "lineup_slot_promotion": round(promotion_component, 2),
            "non_superstar": round(non_superstar_component, 2),
        }
        score = round(_clamp(35.0 + sum(components.values()), 0.0, 100.0), 2)
        confidence = _confidence(profile)
        breakout_candidate = score >= 72 and (barrel_component > 0 or exit_velocity_component > 0) and hr_component >= 0
        lineup_promotion_opportunity = promotion_component >= 4.0 or lineup_component >= 6.0
        emerging_power_trend = (exit_velocity_component + barrel_component + hard_hit_component + hr_component) >= 18.0
        undervalued_young_hitter = not profile.is_superstar and age_component >= 8.0 and score >= 60.0
        notes = _notes(breakout_candidate, lineup_promotion_opportunity, emerging_power_trend, undervalued_young_hitter)
        return YPIResult(
            ypi_score=score,
            ypi_confidence=confidence,
            ypi_grade=_grade(score, confidence),
            breakout_candidate=breakout_candidate,
            lineup_promotion_opportunity=lineup_promotion_opportunity,
            emerging_power_trend=emerging_power_trend,
            undervalued_young_hitter=undervalued_young_hitter,
            components=components,
            notes=notes,
        )


def calculate_ypi_score(profile: YPIProfile) -> YPIResult:
    return YPIEngine().score_profile(profile)


def _age_component(age: int | None) -> float:
    if age is None or age <= 0:
        return 0.0
    if age <= 23:
        return 14.0
    if age <= 25:
        return 10.0
    if age <= 27:
        return 5.0
    if age <= 29:
        return 1.0
    return -4.0


def _experience_component(experience: float) -> float:
    if experience <= 0:
        return 6.0
    if experience <= 1:
        return 5.0
    if experience <= 2:
        return 3.0
    if experience <= 4:
        return 0.0
    return -3.0


def _confidence(profile: YPIProfile) -> float:
    available = 0
    available += 1 if profile.age is not None else 0
    available += 1 if profile.mlb_experience >= 0 else 0
    available += 1 if profile.lineup_movement else 0
    available += 1 if profile.recent_exit_velocity_trend else 0
    available += 1 if profile.recent_barrel_trend else 0
    available += 1 if profile.recent_hard_hit_trend else 0
    available += 1 if profile.hr_trend else 0
    available += 1 if profile.opportunity_growth else 0
    available += 1 if profile.playing_time_growth else 0
    available += 1 if profile.lineup_slot_promotion else 0
    return round(_clamp(available / 10.0, 0.15, 1.0), 2)


def _grade(score: float, confidence: float) -> str:
    adjusted = score * (0.85 + confidence * 0.15)
    if adjusted >= 82:
        return "Elite"
    if adjusted >= 70:
        return "Strong"
    if adjusted >= 58:
        return "Emerging"
    if adjusted >= 42:
        return "Neutral"
    return "Weak"


def _notes(
    breakout_candidate: bool,
    lineup_promotion_opportunity: bool,
    emerging_power_trend: bool,
    undervalued_young_hitter: bool,
) -> List[str]:
    notes: List[str] = []
    if breakout_candidate:
        notes.append("breakout candidate")
    if lineup_promotion_opportunity:
        notes.append("lineup promotion opportunity")
    if emerging_power_trend:
        notes.append("emerging power trend")
    if undervalued_young_hitter:
        notes.append("undervalued young hitter")
    if not notes:
        notes.append("no active YPI boost")
    return notes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
