from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from .formula_config import ScoringWeights, weight
from .models import Batter, HRMatchup, Pitcher, PitcherWeakSpot


@dataclass(frozen=True)
class PitchVulnerabilityInput:
    batter: Batter
    pitcher: Pitcher
    weak_spots: Sequence[PitcherWeakSpot] = ()
    hr_matchups: Sequence[HRMatchup] = ()
    weights: ScoringWeights = field(default_factory=ScoringWeights.defaults)


@dataclass(frozen=True)
class PitchVulnerabilityScore:
    score: float
    label: str
    matched_pitches: List[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _label(score: float) -> str:
    if score >= 15:
        return "elite"
    if score >= 9:
        return "strong"
    if score >= 3:
        return "light"
    if score < 0:
        return "mismatch"
    return "none"


def calculate_pvs(input_data: PitchVulnerabilityInput) -> PitchVulnerabilityScore:
    weights = input_data.weights.pvs
    batter = input_data.batter
    pitcher = input_data.pitcher
    notes: List[str] = []
    matched_pitches: List[str] = []

    matchup_component = 0.0
    quality_component = 0.0
    for matchup in input_data.hr_matchups:
        if matchup.batter_name.lower() != batter.name.lower():
            continue
        if matchup.pitcher_name.lower() != pitcher.name.lower():
            continue
        matched_pitches.append(matchup.pitch)
        matchup_component += matchup.matchup_score or weight(weights, "default_matchup_score", 6.0)
        if matchup.exit_velo and matchup.exit_velo >= weight(weights, "exit_velo_threshold", 105.0):
            quality_component += weight(weights, "exit_velo_bonus", 4.0)
            notes.append("plus exit velocity")
        if matchup.distance and matchup.distance >= weight(weights, "distance_threshold", 400.0):
            quality_component += weight(weights, "distance_bonus", 3.0)
            notes.append("400+ foot contact")
        if matchup.angle and weight(weights, "launch_angle_min", 20.0) <= matchup.angle <= weight(weights, "launch_angle_max", 35.0):
            quality_component += weight(weights, "launch_angle_bonus", 2.0)
            notes.append("HR launch angle")

    matchup_pitch_names = {pitch.lower() for pitch in matched_pitches if pitch}
    weak_spot_component = 0.0
    for weak_spot in input_data.weak_spots:
        if weak_spot.pitcher_name.lower() != pitcher.name.lower():
            continue
        if not matchup_pitch_names or weak_spot.pitch.lower() in matchup_pitch_names:
            matched_pitches.append(weak_spot.pitch)
            weak_spot_component += weak_spot.weakness_score

    pitch_mix_component = 0.0
    if batter.pitch_mix_score >= 7:
        pitch_mix_component = weight(weights, "pitch_mix_elite", 8.0)
    elif batter.pitch_mix_score >= 6:
        pitch_mix_component = weight(weights, "pitch_mix_strong", 5.0)
    elif batter.pitch_mix_score >= 5:
        pitch_mix_component = weight(weights, "pitch_mix_light", 2.0)
    elif 0 < batter.pitch_mix_score < 4:
        pitch_mix_component = weight(weights, "pitch_mix_poor", -4.0)
        notes.append("poor pitch mix fit")

    pitcher_projection_component = (
        pitcher.projected_hr * weight(weights, "projected_hr_multiplier", 2.5)
    ) + max(0.0, pitcher.projected_hits - weight(weights, "projected_hits_baseline", 4.5))

    components = {
        "hr_matchup": round(matchup_component, 2),
        "quality_contact": round(quality_component, 2),
        "weak_spot_collision": round(weak_spot_component, 2),
        "pitch_mix": round(pitch_mix_component, 2),
        "pitcher_projection": round(pitcher_projection_component, 2),
    }
    score = round(_clamp(sum(components.values()), weight(weights, "score_min", -8.0), weight(weights, "score_max", 24.0)), 2)
    return PitchVulnerabilityScore(
        score=score,
        label=_label(score),
        matched_pitches=sorted({pitch for pitch in matched_pitches if pitch}),
        components=components,
        notes=notes,
    )
