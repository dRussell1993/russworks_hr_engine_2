from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ParkFactorProfile:
    park_name: str
    handedness: str = "UNKNOWN"
    pull_side: str = ""
    weather_boost: float = 0.0
    roof_status: str = "open"
    wind_speed: float = 0.0
    wind_direction: str = ""
    temperature: float = 70.0
    humidity: float = 0.0
    hr_park_factor: float = 0.0
    left_field_carry: float = 0.0
    center_field_carry: float = 0.0
    right_field_carry: float = 0.0


@dataclass(frozen=True)
class ParkFactorResult:
    park_factor_score: float
    confidence: float
    grade: str
    raw_park_component: float = 0.0
    same_day_weather_component: float = 0.0
    path_component: float = 0.0
    roof_component: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class ParkFactorEngine:
    def score_profile(self, profile: ParkFactorProfile) -> ParkFactorResult:
        pull_side = _pull_side(profile)
        raw_park = _clamp(profile.hr_park_factor * 28.0, -14.0, 22.0)
        path = _path_component(profile, pull_side)
        weather = _same_day_weather_component(profile)
        roof = _roof_component(profile)
        components = {
            "raw_park_factor": round(raw_park, 2),
            "pull_side_path": round(path, 2),
            "same_day_weather": round(weather, 2),
            "roof": round(roof, 2),
        }
        score = round(_clamp(45.0 + sum(components.values()), 0.0, 100.0), 2)
        confidence = _confidence(profile)
        return ParkFactorResult(
            park_factor_score=score,
            confidence=confidence,
            grade=_grade(score, confidence),
            raw_park_component=components["raw_park_factor"],
            same_day_weather_component=components["same_day_weather"],
            path_component=components["pull_side_path"],
            roof_component=components["roof"],
            components=components,
            notes=_notes(profile, pull_side, raw_park, path, weather, roof),
        )


def calculate_park_factor_score(profile: ParkFactorProfile) -> ParkFactorResult:
    return ParkFactorEngine().score_profile(profile)


def _pull_side(profile: ParkFactorProfile) -> str:
    explicit = profile.pull_side.strip().lower().replace(" ", "_")
    if explicit in {"left_field", "center_field", "right_field", "lf", "cf", "rf"}:
        return {"lf": "left_field", "cf": "center_field", "rf": "right_field"}.get(explicit, explicit)
    handedness = profile.handedness.strip().upper()
    if handedness == "R":
        return "left_field"
    if handedness == "L":
        return "right_field"
    return "center_field"


def _path_component(profile: ParkFactorProfile, pull_side: str) -> float:
    carry = {
        "left_field": profile.left_field_carry,
        "center_field": profile.center_field_carry,
        "right_field": profile.right_field_carry,
    }.get(pull_side, profile.center_field_carry)
    return _clamp(carry * 1.35, -10.0, 16.0)


def _same_day_weather_component(profile: ParkFactorProfile) -> float:
    weather = _clamp(profile.weather_boost / 2.0, -8.0, 10.0)
    temperature = _clamp((profile.temperature - 70.0) / 5.5, -5.0, 7.0)
    humidity = _clamp((profile.humidity - 45.0) / 18.0, -3.0, 4.0)
    wind_direction = profile.wind_direction.lower()
    if "out" in wind_direction:
        wind = _clamp(profile.wind_speed / 3.0, 0.0, 8.0)
    elif "in" in wind_direction:
        wind = -_clamp(profile.wind_speed / 3.5, 0.0, 7.0)
    else:
        wind = 0.0
    return _clamp(weather + temperature + humidity + wind, -14.0, 18.0)


def _roof_component(profile: ParkFactorProfile) -> float:
    roof = profile.roof_status.strip().lower()
    if roof == "closed" or "roof closed" in roof:
        return -8.0
    if roof in {"open", "retractable open"}:
        return 0.0
    return -2.0 if "closed" in roof else 0.0


def _confidence(profile: ParkFactorProfile) -> float:
    available = 0
    available += 1 if profile.park_name else 0
    available += 1 if profile.handedness else 0
    available += 1 if profile.pull_side else 0
    available += 1 if profile.weather_boost else 0
    available += 1 if profile.roof_status else 0
    available += 1 if profile.wind_speed else 0
    available += 1 if profile.wind_direction else 0
    available += 1 if profile.temperature else 0
    available += 1 if profile.humidity else 0
    available += 1 if profile.hr_park_factor else 0
    available += 1 if profile.left_field_carry else 0
    available += 1 if profile.center_field_carry else 0
    available += 1 if profile.right_field_carry else 0
    return round(_clamp(available / 13.0, 0.15, 1.0), 2)


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
    return "Suppressive"


def _notes(
    profile: ParkFactorProfile,
    pull_side: str,
    raw_park: float,
    path: float,
    weather: float,
    roof: float,
) -> List[str]:
    notes: List[str] = [f"{pull_side.replace('_', ' ')} path"]
    if raw_park >= 8.0:
        notes.append("high raw HR park factor")
    elif raw_park <= -6.0:
        notes.append("suppressive raw HR park factor")
    if path >= 6.0:
        notes.append("pull-side carry boost")
    elif path <= -4.0:
        notes.append("pull-side carry suppression")
    if weather >= 6.0:
        notes.append("weather-assisted carry")
    elif weather <= -5.0:
        notes.append("weather suppresses carry")
    if roof < 0.0:
        notes.append("roof suppression")
    if "coors" in profile.park_name.lower():
        notes.append("Coors-style carry profile")
    return notes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
