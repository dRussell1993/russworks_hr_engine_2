from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import List, Sequence

from .formula_config import ScoringWeights, weight
from .models import Batter, Pitcher


@dataclass(frozen=True)
class TeamAttackGradeInput:
    team: str
    batters: Sequence[Batter]
    opposing_pitcher: Pitcher
    environment_score: float = 0.0
    umpire_score: float = 0.0
    team_hr_momentum: float = 0.0
    run_production_concentration: float = 0.0
    postmortem_archetype_bonus: float = 0.0
    weights: ScoringWeights = field(default_factory=ScoringWeights.defaults)


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
    if score >= 66:
        return "B"
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
        return TeamAttackGrade(input_data.team, 0.0, "D", {}, ["no batters supplied"])

    weights = input_data.weights.tag
    all_hr = [b.hr_pct for b in batters]
    top_half = [b.hr_pct for b in batters if 1 <= b.lineup_slot <= 5]
    viable_count = sum(1 for b in batters if b.hr_pct >= 12)
    top_half_average = mean(top_half or all_hr)
    full_lineup_average = mean(all_hr)

    components = {
        "base": weight(weights, "base", 45.0),
        "full_lineup_power": round(full_lineup_average * weight(weights, "full_lineup_power", 1.6), 2),
        "top_half_power": round(top_half_average * weight(weights, "top_half_power", 1.3), 2),
        "viable_hr_bats": round(viable_count * weight(weights, "viable_bat", 2.0), 2),
        "pitcher_attackability": round((pitcher_attackability(input_data.opposing_pitcher) - 50.0) * weight(weights, "pitcher_attackability", 0.6), 2),
        "environment": round(input_data.environment_score * weight(weights, "environment", 0.8), 2),
        "umpire": round(input_data.umpire_score * weight(weights, "umpire", 0.5), 2),
        "team_hr_momentum": round(input_data.team_hr_momentum * weight(weights, "team_hr_momentum", 1.0), 2),
        "run_production_concentration": round(input_data.run_production_concentration * weight(weights, "run_production_concentration", 1.0), 2),
        "postmortem_archetype": round(input_data.postmortem_archetype_bonus * weight(weights, "postmortem_archetype", 1.0), 2),
    }
    score = round(_clamp(sum(components.values()), 20.0, 100.0), 2)

    notes: List[str] = []
    if viable_count >= 4:
        notes.append("multiple viable HR bats")
    if top_half_average >= full_lineup_average:
        notes.append("top-half strength")
    if components["pitcher_attackability"] >= 5:
        notes.append("attackable pitcher")
    if components["environment"] >= 5:
        notes.append("environment boost")

    return TeamAttackGrade(team=input_data.team, score=score, grade=grade_score(score), components=components, notes=notes)
