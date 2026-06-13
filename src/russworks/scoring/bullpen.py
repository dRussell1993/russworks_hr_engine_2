from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class RelieverProfile:
    name: str
    pitch_mix: dict[str, float] = field(default_factory=dict)
    hr_tendencies: float = 0.0
    handedness: str = ""
    leverage_role: str = ""


@dataclass(frozen=True)
class BullpenProfile:
    team: str
    bullpen_era: float = 0.0
    bullpen_hr_per_9: float = 0.0
    bullpen_xfip: float = 0.0
    strikeout_rate: float = 0.0
    walk_rate: float = 0.0
    recent_bullpen_workload: float = 0.0
    previous_3_day_workload: float = 0.0
    closer_available: bool = True
    relievers: List[RelieverProfile] = field(default_factory=list)


@dataclass(frozen=True)
class BullpenExposureResult:
    bullpen_exposure_score: float
    confidence: float
    grade: str
    weak_bullpen_environment: bool = False
    heavy_bullpen_exposure: bool = False
    overworked_bullpen: bool = False
    closer_unavailable: bool = False
    hr_prone_relief_corps: bool = False
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class BullpenExposureEngine:
    def score_profile(self, profile: BullpenProfile) -> BullpenExposureResult:
        era_component = _clamp((profile.bullpen_era - 3.80) * 8.0, -10.0, 20.0)
        hr_component = _clamp((profile.bullpen_hr_per_9 - 1.00) * 18.0, -8.0, 24.0)
        xfip_component = _clamp((profile.bullpen_xfip - 4.00) * 7.0, -8.0, 18.0)
        strikeout_component = _clamp((22.0 - profile.strikeout_rate) * 0.75, -8.0, 12.0)
        walk_component = _clamp((profile.walk_rate - 8.0) * 1.20, -6.0, 14.0)
        recent_workload_component = _clamp((profile.recent_bullpen_workload - 3.0) * 4.0, -4.0, 18.0)
        three_day_workload_component = _clamp((profile.previous_3_day_workload - 9.0) * 1.6, -4.0, 18.0)
        closer_component = 9.0 if not profile.closer_available else 0.0
        reliever_component = _reliever_component(profile.relievers)

        components = {
            "bullpen_era": round(era_component, 2),
            "bullpen_hr_per_9": round(hr_component, 2),
            "bullpen_xfip": round(xfip_component, 2),
            "strikeout_rate": round(strikeout_component, 2),
            "walk_rate": round(walk_component, 2),
            "recent_bullpen_workload": round(recent_workload_component, 2),
            "previous_3_day_workload": round(three_day_workload_component, 2),
            "closer_availability": round(closer_component, 2),
            "reliever_hr_tendencies": round(reliever_component, 2),
        }
        score = round(_clamp(38.0 + sum(components.values()), 0.0, 100.0), 2)
        confidence = _confidence(profile)
        weak_environment = profile.bullpen_era >= 4.50 or profile.bullpen_xfip >= 4.40
        heavy_exposure = profile.recent_bullpen_workload >= 4.5 or profile.previous_3_day_workload >= 11.0
        overworked = profile.recent_bullpen_workload >= 5.0 or profile.previous_3_day_workload >= 13.0
        closer_unavailable = not profile.closer_available
        hr_prone = profile.bullpen_hr_per_9 >= 1.25 or any(reliever.hr_tendencies >= 1.25 for reliever in profile.relievers)
        return BullpenExposureResult(
            bullpen_exposure_score=score,
            confidence=confidence,
            grade=_grade(score, confidence),
            weak_bullpen_environment=weak_environment,
            heavy_bullpen_exposure=heavy_exposure,
            overworked_bullpen=overworked,
            closer_unavailable=closer_unavailable,
            hr_prone_relief_corps=hr_prone,
            components=components,
            notes=_notes(weak_environment, heavy_exposure, overworked, closer_unavailable, hr_prone),
        )


def calculate_bullpen_exposure_score(profile: BullpenProfile) -> BullpenExposureResult:
    return BullpenExposureEngine().score_profile(profile)


def _reliever_component(relievers: List[RelieverProfile]) -> float:
    if not relievers:
        return 0.0
    component = 0.0
    for reliever in relievers:
        component += _clamp((reliever.hr_tendencies - 1.0) * 6.0, -2.0, 8.0)
        if _role(reliever.leverage_role) in {"closer", "setup", "high_leverage"} and reliever.hr_tendencies >= 1.20:
            component += 2.0
    return _clamp(component, -5.0, 18.0)


def _confidence(profile: BullpenProfile) -> float:
    available = 0
    available += 1 if profile.team else 0
    available += 1 if profile.bullpen_era else 0
    available += 1 if profile.bullpen_hr_per_9 else 0
    available += 1 if profile.bullpen_xfip else 0
    available += 1 if profile.strikeout_rate else 0
    available += 1 if profile.walk_rate else 0
    available += 1 if profile.recent_bullpen_workload else 0
    available += 1 if profile.previous_3_day_workload else 0
    available += 1
    available += min(3, len(profile.relievers))
    return round(_clamp(available / 12.0, 0.15, 1.0), 2)


def _grade(score: float, confidence: float) -> str:
    adjusted = score * (0.86 + confidence * 0.14)
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
    weak_environment: bool,
    heavy_exposure: bool,
    overworked: bool,
    closer_unavailable: bool,
    hr_prone: bool,
) -> List[str]:
    notes: List[str] = []
    if weak_environment:
        notes.append("weak bullpen environment")
    if heavy_exposure:
        notes.append("heavy bullpen exposure")
    if overworked:
        notes.append("overworked bullpen")
    if closer_unavailable:
        notes.append("closer unavailable")
    if hr_prone:
        notes.append("HR-prone relief corps")
    if not notes:
        notes.append("neutral bullpen exposure")
    return notes


def _role(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
