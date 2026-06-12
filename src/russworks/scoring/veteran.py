from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class VeteranProfile:
    batter_name: str
    age: int | None = None
    mlb_service_time: float = 0.0
    historical_hr_production: float = 0.0
    historical_barrel_rate: float = 0.0
    historical_hard_hit_rate: float = 0.0
    current_barrel_rate: float = 0.0
    current_hard_hit_rate: float = 0.0
    recent_hr_drought: float = 0.0
    lineup_slot: int | None = None
    team_cluster_quality: float = 0.0
    recent_exit_velocity_trend: float = 0.0
    is_superstar: bool = False


@dataclass(frozen=True)
class VeteranBounceResult:
    veteran_bounce_score: float
    confidence: float
    grade: str
    healthy_underlying_metrics: bool
    temporary_hr_drought: bool
    bounce_back_candidate: bool
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class VeteranBounceEngine:
    def score_profile(self, profile: VeteranProfile) -> VeteranBounceResult:
        healthy_metrics = _has_healthy_underlying_metrics(profile)
        age_component = _age_component(profile.age)
        service_component = _clamp(profile.mlb_service_time * 1.2, -4.0, 10.0)
        historical_power_component = _clamp(profile.historical_hr_production * 0.9, -8.0, 16.0)
        historical_barrel_component = _clamp((profile.historical_barrel_rate - 7.0) * 1.2, -8.0, 14.0)
        historical_hard_hit_component = _clamp((profile.historical_hard_hit_rate - 38.0) * 0.45, -8.0, 12.0)
        current_barrel_component = _clamp((profile.current_barrel_rate - 7.0) * 1.8, -10.0, 18.0)
        current_hard_hit_component = _clamp((profile.current_hard_hit_rate - 38.0) * 0.65, -10.0, 16.0)
        stability_component = _metric_stability_component(profile)
        drought_component = _drought_component(profile)
        lineup_component = _lineup_component(profile.lineup_slot)
        cluster_component = _clamp((profile.team_cluster_quality - 70.0) * 0.18, -6.0, 10.0)
        exit_velocity_component = _clamp(profile.recent_exit_velocity_trend * 3.0, -8.0, 14.0)
        non_superstar_component = 3.0 if not profile.is_superstar else 0.0
        unsupported_name_value_component = -12.0 if profile.is_superstar and not healthy_metrics else 0.0

        components = {
            "age": round(age_component, 2),
            "mlb_service_time": round(service_component, 2),
            "historical_hr_production": round(historical_power_component, 2),
            "historical_barrel_rate": round(historical_barrel_component, 2),
            "historical_hard_hit_rate": round(historical_hard_hit_component, 2),
            "current_barrel_rate": round(current_barrel_component, 2),
            "current_hard_hit_rate": round(current_hard_hit_component, 2),
            "metric_stability": round(stability_component, 2),
            "recent_hr_drought": round(drought_component, 2),
            "lineup_slot": round(lineup_component, 2),
            "team_cluster_quality": round(cluster_component, 2),
            "recent_exit_velocity_trend": round(exit_velocity_component, 2),
            "non_superstar": round(non_superstar_component, 2),
            "unsupported_name_value": round(unsupported_name_value_component, 2),
        }
        score = round(_clamp(25.0 + sum(components.values()), 0.0, 100.0), 2)
        confidence = _confidence(profile)
        temporary_drought = profile.recent_hr_drought >= 8.0 and healthy_metrics
        bounce_back = score >= 68.0 and healthy_metrics and (temporary_drought or profile.recent_exit_velocity_trend >= 1.0)
        return VeteranBounceResult(
            veteran_bounce_score=score,
            confidence=confidence,
            grade=_grade(score, confidence),
            healthy_underlying_metrics=healthy_metrics,
            temporary_hr_drought=temporary_drought,
            bounce_back_candidate=bounce_back,
            components=components,
            notes=_notes(healthy_metrics, temporary_drought, bounce_back, profile.is_superstar),
        )


def calculate_veteran_bounce_score(profile: VeteranProfile) -> VeteranBounceResult:
    return VeteranBounceEngine().score_profile(profile)


def _age_component(age: int | None) -> float:
    if age is None or age <= 0:
        return 0.0
    if 30 <= age <= 34:
        return 8.0
    if 35 <= age <= 37:
        return 5.0
    if 28 <= age <= 29:
        return 3.0
    if 38 <= age <= 40:
        return 1.0
    if age > 40:
        return -4.0
    return -2.0


def _lineup_component(slot: int | None) -> float:
    if slot is None or slot <= 0:
        return -4.0
    if slot == 4:
        return 10.0
    if slot == 3:
        return 8.0
    if slot in {1, 2, 5}:
        return 6.0
    if slot == 6:
        return 1.0
    if slot == 7:
        return -2.0
    return -5.0


def _metric_stability_component(profile: VeteranProfile) -> float:
    barrel_gap = abs(profile.current_barrel_rate - profile.historical_barrel_rate)
    hard_hit_gap = abs(profile.current_hard_hit_rate - profile.historical_hard_hit_rate)
    if barrel_gap <= 1.5 and hard_hit_gap <= 4.0:
        return 9.0
    if barrel_gap <= 3.0 and hard_hit_gap <= 7.0:
        return 5.0
    if profile.current_barrel_rate >= profile.historical_barrel_rate or profile.current_hard_hit_rate >= profile.historical_hard_hit_rate:
        return 3.0
    return -6.0


def _drought_component(profile: VeteranProfile) -> float:
    if profile.recent_hr_drought <= 0:
        return 0.0
    if _has_healthy_underlying_metrics(profile):
        return _clamp(profile.recent_hr_drought * 0.8, 0.0, 10.0)
    return -_clamp(profile.recent_hr_drought * 0.5, 0.0, 8.0)


def _has_healthy_underlying_metrics(profile: VeteranProfile) -> bool:
    return (
        profile.current_barrel_rate >= 8.0
        and profile.current_hard_hit_rate >= 40.0
        and profile.historical_hr_production >= 12.0
    )


def _confidence(profile: VeteranProfile) -> float:
    available = 0
    available += 1 if profile.age is not None else 0
    available += 1 if profile.mlb_service_time else 0
    available += 1 if profile.historical_hr_production else 0
    available += 1 if profile.historical_barrel_rate else 0
    available += 1 if profile.historical_hard_hit_rate else 0
    available += 1 if profile.current_barrel_rate else 0
    available += 1 if profile.current_hard_hit_rate else 0
    available += 1 if profile.recent_hr_drought else 0
    available += 1 if profile.lineup_slot is not None else 0
    available += 1 if profile.team_cluster_quality else 0
    available += 1 if profile.recent_exit_velocity_trend else 0
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
    healthy_metrics: bool,
    temporary_drought: bool,
    bounce_back: bool,
    is_superstar: bool,
) -> List[str]:
    notes: List[str] = []
    if healthy_metrics:
        notes.append("healthy underlying veteran metrics")
    if temporary_drought:
        notes.append("temporary HR drought")
    if bounce_back:
        notes.append("bounce-back candidate")
    if not is_superstar:
        notes.append("does not require superstar status")
    if is_superstar and not healthy_metrics:
        notes.append("unsupported name-value guardrail")
    if not notes:
        notes.append("no active Veteran Bounce boost")
    return notes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
