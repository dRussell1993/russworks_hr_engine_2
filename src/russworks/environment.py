from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .models import GameEnvironment


@dataclass(frozen=True)
class EnvironmentScoreInput:
    environment: GameEnvironment


@dataclass(frozen=True)
class EnvironmentScore:
    score: float
    label: str
    components: dict[str, float]
    notes: List[str] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _label(score: float) -> str:
    if score >= 15:
        return "extreme"
    if score >= 6:
        return "positive"
    if score <= -5:
        return "negative"
    return "neutral"


def calculate_environment_score(input_data: EnvironmentScoreInput) -> EnvironmentScore:
    env = input_data.environment
    notes: List[str] = []

    weather_hr = _clamp(env.weather_hr_pct / 4.0, -8.0, 12.0)
    distance = _clamp(env.weather_distance_ft / 3.0, -6.0, 8.0)
    park = _clamp(env.park_hr_factor * 5.0, -5.0, 8.0)
    temperature = _clamp((env.temperature_f - 70.0) / 6.0, -4.0, 5.0)

    wind_direction = env.wind_direction.lower()
    if "out" in wind_direction:
        wind = _clamp(env.wind_mph / 3.0, 0.0, 7.0)
        notes.append("wind out")
    elif "in" in wind_direction:
        wind = -_clamp(env.wind_mph / 4.0, 0.0, 6.0)
        notes.append("wind in")
    else:
        wind = 0.0

    roof = -2.0 if env.roof.lower() == "closed" or "roof closed" in env.roof.lower() else 0.0
    if roof:
        notes.append("closed roof")

    if "coors" in env.park.lower():
        park += 10.0
        notes.append("coors boost")

    components = {
        "weather_hr": round(weather_hr, 2),
        "distance": round(distance, 2),
        "park": round(park, 2),
        "temperature": round(temperature, 2),
        "wind": round(wind, 2),
        "roof": round(roof, 2),
    }
    score = round(sum(components.values()), 2)
    return EnvironmentScore(score=score, label=_label(score), components=components, notes=notes)
