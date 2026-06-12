from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from ..config.weights import ScoringWeights, weight
from ..models import Batter
from .tag import grade_score


@dataclass(frozen=True)
class ClusterParticipationInput:
    team: str
    batters: Sequence[Batter]
    tag_score: float
    environment_score: float = 0.0
    postmortem_archetype_bonus: float = 0.0
    weights: ScoringWeights = field(default_factory=ScoringWeights.defaults)


@dataclass(frozen=True)
class ClusterParticipationScore:
    team: str
    score: float
    grade: str
    core_batters: List[str]
    components: dict[str, float]
    notes: List[str] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def calculate_cps(input_data: ClusterParticipationInput) -> ClusterParticipationScore:
    batters = list(input_data.batters)
    if not batters:
        return ClusterParticipationScore(input_data.team, 0.0, "D", [], {}, ["no batters supplied"])

    weights = input_data.weights.cps
    ranked = sorted(batters, key=lambda batter: batter.hr_pct, reverse=True)
    core = ranked[:4]
    top_hr_sum = sum(b.hr_pct for b in core)
    top_five_alignment = sum(1 for b in core if 1 <= b.lineup_slot <= 5)
    viable_count = sum(1 for b in batters if b.hr_pct >= 12)
    cluster_spacing = _cluster_spacing_score(core, input_data.weights)
    special_layer_count = sum(1 for b in core if _has_special_layer(b))

    components = {
        "base": weight(weights, "base", 35.0),
        "concentration": round(top_hr_sum * weight(weights, "concentration", 0.7), 2),
        "top_five_alignment": round(top_five_alignment * weight(weights, "top_five_alignment", 4.0), 2),
        "viable_bats": round(viable_count * weight(weights, "viable_bat", 2.0), 2),
        "tag_support": round((input_data.tag_score - 60.0) * weight(weights, "tag_support", 0.35), 2),
        "cluster_spacing": round(cluster_spacing, 2),
        "special_layers": round(special_layer_count * weight(weights, "special_layer", 1.5), 2),
        "environment": round(input_data.environment_score * weight(weights, "environment", 0.5), 2),
        "postmortem_archetype": round(input_data.postmortem_archetype_bonus * weight(weights, "postmortem_archetype", 1.0), 2),
    }
    score = round(_clamp(sum(components.values()), 20.0, 100.0), 2)

    notes: List[str] = []
    if top_five_alignment >= 3:
        notes.append("cluster lives in top five")
    if viable_count >= 4:
        notes.append("deep viable pool")
    if cluster_spacing > 0:
        notes.append("tight lineup cluster")
    if special_layer_count:
        notes.append("special-layer participation")

    return ClusterParticipationScore(
        team=input_data.team,
        score=score,
        grade=grade_score(score),
        core_batters=[b.name for b in core],
        components=components,
        notes=notes,
    )


def _cluster_spacing_score(core: Sequence[Batter], weights: ScoringWeights) -> float:
    slots = sorted(b.lineup_slot for b in core if b.lineup_slot)
    if len(slots) < 2:
        return 0.0
    span = slots[-1] - slots[0]
    if span <= 3:
        return weight(weights.cps, "tight_cluster", 6.0)
    if span <= 5:
        return weight(weights.cps, "loose_cluster", 3.0)
    return 0.0


def _has_special_layer(batter: Batter) -> bool:
    tags = " ".join(batter.tags).lower()
    return any(key in tags for key in ["ypi", "young", "rookie", "prospect", "catcher", "small sample"])
