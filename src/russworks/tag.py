from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import List, Sequence

from .models import Batter, Pitcher


@dataclass(frozen=True)
class TeamAttackGradeInput:
    team: str
    batters: Sequence[Batter]
    opposing_pitcher: Pitcher
    environment_score: float = 0.0
    umpire_score: float = 0.0
    postmortem_archetype_bonus: float = 0.0


@dataclass(frozen=True)
class TeamAttackGrade:
    team: str
    score: float
    grade: str
    components: dict[str, float]
    notes: List[str] = field(default_factory=list)


def grade_score(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 84:
        return "A"
    if score >= 78:
        return "A-"
    if score >= 72:
        return "B+"
    if score >= 66:
        return "B"
    if score >= 60:
        return "B-"
    if score >= 52:
        return "C"
    return "D"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def pitcher_attackability(pitcher: Pitcher) -> float:
    score = 50.0
    score += pitcher.projected_hr * 14.0
    score += max(0.0, pitcher.projected_hits - 4.5) * 2.0
    score += max(0.0, pitcher.projected_bb - 1.5) * 2.0
    for tag in pitcher.tags:
        lowered = tag.lower()
        if any(key in lowered for key in ["hitter", "meatball", "struggling", "short leash", "small sample"]):
            score += 5.0
        if any(key in lowered for key in ["hr stingy", "ground ball", "ace", "top of rotation"]):
            score -= 6.0
        if "control issues" in lowered:
            score += 4.0
        if any(key in lowered for key in ["swing", "strikeout", "k upside"]):
            score -= 3.0
    return _clamp(score, 20.0, 90.0)


def calculate_tag(input_data: TeamAttackGradeInput) -> TeamAttackGrade:
    batters = list(input_data.batters)
    if not batters:
        return TeamAttackGrade(
            team=input_data.team,
            score=0.0,
            grade="D",
            components={},
            notes=["no batters supplied"],
        )

    top_half = [b.hr_pct for b in batters if 1 <= b.lineup_slot <= 5]
    all_hr = [b.hr_pct for b in batters]
    viable_count = sum(1 for b in batters if b.hr_pct >= 12)
    top_half_power = mean(top_half or all_hr) * 1.3
    full_lineup_power = mean(all_hr) * 1.6
    viable_power = viable_count * 2.0
    pitcher_component = (pitcher_attackability(input_data.opposing_pitcher) - 50.0) * 0.6
    environment_component = input_data.environment_score * 0.8
    umpire_component = input_data.umpire_score * 0.5

    components = {
        "base": 45.0,
        "full_lineup_power": round(full_lineup_power, 2),
        "top_half_power": round(top_half_power, 2),
        "viable_power": round(viable_power, 2),
        "pitcher_attackability": round(pitcher_component, 2),
        "environment": round(environment_component, 2),
        "umpire": round(umpire_component, 2),
        "postmortem_archetype": round(input_data.postmortem_archetype_bonus, 2),
    }
    score = round(_clamp(sum(components.values()), 20.0, 100.0), 2)

    notes: List[str] = []
    if viable_count >= 4:
        notes.append("multiple viable HR bats")
    if mean(top_half or all_hr) >= mean(all_hr):
        notes.append("top-half strength")
    if pitcher_component >= 5:
        notes.append("attackable pitcher")
    if environment_component >= 5:
        notes.append("environment boost")

    return TeamAttackGrade(team=input_data.team, score=score, grade=grade_score(score), components=components, notes=notes)
