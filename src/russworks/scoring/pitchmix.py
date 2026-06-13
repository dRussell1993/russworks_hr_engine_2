from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PitchMixProfile:
    pitcher_name: str
    pitch_types: List[str] = field(default_factory=list)
    pitch_usage_percentages: dict[str, float] = field(default_factory=dict)
    primary_pitch: str = ""
    secondary_pitch: str = ""


@dataclass(frozen=True)
class BatterPitchProfile:
    batter_name: str
    hr_rate_by_pitch_type: dict[str, float] = field(default_factory=dict)
    barrel_rate_by_pitch_type: dict[str, float] = field(default_factory=dict)
    slugging_by_pitch_type: dict[str, float] = field(default_factory=dict)
    iso_by_pitch_type: dict[str, float] = field(default_factory=dict)
    whiff_rate_by_pitch_type: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PitchMixMatchupResult:
    pitch_mix_matchup_score: float
    confidence: float
    grade: str
    matched_pitches: List[str] = field(default_factory=list)
    primary_pitch_collision: bool = False
    severe_primary_weakness: bool = False
    multiple_positive_collisions: bool = False
    elite_pitch_type_specialist: bool = False
    components: dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class PitchMixEngine:
    def score_matchup(self, pitcher: PitchMixProfile, batter: BatterPitchProfile) -> PitchMixMatchupResult:
        pitch_usage = _normalized_pitch_usage(pitcher)
        matched_pitches = [pitch for pitch in pitch_usage if _has_batter_pitch_data(batter, pitch)]
        confidence = _confidence(pitcher, batter, matched_pitches)
        if not pitch_usage:
            return PitchMixMatchupResult(
                pitch_mix_matchup_score=0.0,
                confidence=confidence,
                grade="Weak",
                components={"missing_pitch_mix": 0.0},
                notes=["missing pitcher pitch mix"],
            )

        components: dict[str, float] = {}
        positive_collisions = 0
        weighted_component = 0.0
        best_pitch_component = -100.0
        best_pitch_usage = 0.0
        primary_pitch = _norm(pitcher.primary_pitch)
        secondary_pitch = _norm(pitcher.secondary_pitch)

        for pitch, usage_share in pitch_usage.items():
            raw_pitch_score = _pitch_component(batter, pitch)
            pitch_multiplier = 1.35 if pitch == primary_pitch else 1.10 if pitch == secondary_pitch else 1.0
            usage_component = raw_pitch_score * usage_share * pitch_multiplier
            components[f"{pitch}_component"] = round(usage_component, 2)
            weighted_component += usage_component
            if raw_pitch_score >= 18.0 and usage_share >= 0.15:
                positive_collisions += 1
            if raw_pitch_score > best_pitch_component:
                best_pitch_component = raw_pitch_score
                best_pitch_usage = usage_share

        primary_pitch_collision = primary_pitch in pitch_usage and _pitch_component(batter, primary_pitch) >= 18.0
        severe_primary_weakness = primary_pitch in pitch_usage and _severe_primary_weakness(batter, primary_pitch)
        multiple_positive_collisions = positive_collisions >= 2
        elite_pitch_type_specialist = best_pitch_component >= 32.0 and best_pitch_usage >= 0.25

        bonus = 0.0
        if primary_pitch_collision:
            bonus += 9.0
        if multiple_positive_collisions:
            bonus += 6.0
        if elite_pitch_type_specialist:
            bonus += 7.0
        if severe_primary_weakness:
            bonus -= 18.0

        components["weighted_pitch_mix"] = round(weighted_component, 2)
        components["primary_pitch_bonus"] = 9.0 if primary_pitch_collision else 0.0
        components["multiple_collision_bonus"] = 6.0 if multiple_positive_collisions else 0.0
        components["specialist_bonus"] = 7.0 if elite_pitch_type_specialist else 0.0
        components["primary_weakness_penalty"] = -18.0 if severe_primary_weakness else 0.0

        score = round(_clamp(45.0 + weighted_component + bonus, 0.0, 100.0), 2)
        return PitchMixMatchupResult(
            pitch_mix_matchup_score=score,
            confidence=confidence,
            grade=_grade(score, confidence),
            matched_pitches=matched_pitches,
            primary_pitch_collision=primary_pitch_collision,
            severe_primary_weakness=severe_primary_weakness,
            multiple_positive_collisions=multiple_positive_collisions,
            elite_pitch_type_specialist=elite_pitch_type_specialist,
            components=components,
            notes=_notes(
                primary_pitch_collision,
                severe_primary_weakness,
                multiple_positive_collisions,
                elite_pitch_type_specialist,
            ),
        )


def calculate_pitch_mix_matchup_score(
    pitcher: PitchMixProfile,
    batter: BatterPitchProfile,
) -> PitchMixMatchupResult:
    return PitchMixEngine().score_matchup(pitcher, batter)


def _normalized_pitch_usage(profile: PitchMixProfile) -> dict[str, float]:
    pitches = [_norm(pitch) for pitch in profile.pitch_types if _norm(pitch)]
    for pitch in profile.pitch_usage_percentages:
        normalized = _norm(pitch)
        if normalized and normalized not in pitches:
            pitches.append(normalized)
    if not pitches:
        return {}

    raw_usage = {_norm(pitch): max(float(usage), 0.0) for pitch, usage in profile.pitch_usage_percentages.items()}
    if raw_usage:
        total = sum(raw_usage.get(pitch, 0.0) for pitch in pitches)
        if total > 0:
            return {pitch: raw_usage.get(pitch, 0.0) / total for pitch in pitches}

    primary = _norm(profile.primary_pitch) or pitches[0]
    secondary = _norm(profile.secondary_pitch)
    remaining = [pitch for pitch in pitches if pitch not in {primary, secondary}]
    usage: dict[str, float] = {pitch: 0.0 for pitch in pitches}
    usage[primary] = 0.55
    if secondary and secondary in usage:
        usage[secondary] = 0.30
    leftover = max(0.0, 1.0 - sum(usage.values()))
    if remaining:
        for pitch in remaining:
            usage[pitch] = leftover / len(remaining)
    elif secondary not in usage and pitches:
        usage[pitches[0]] += leftover
    total = sum(usage.values()) or 1.0
    return {pitch: value / total for pitch, value in usage.items()}


def _pitch_component(profile: BatterPitchProfile, pitch: str) -> float:
    hr_rate = _metric(profile.hr_rate_by_pitch_type, pitch)
    barrel_rate = _metric(profile.barrel_rate_by_pitch_type, pitch)
    slugging = _metric(profile.slugging_by_pitch_type, pitch)
    iso = _metric(profile.iso_by_pitch_type, pitch)
    whiff_rate = _metric(profile.whiff_rate_by_pitch_type, pitch)
    component = 0.0
    component += _clamp((hr_rate - 2.0) * 2.4, -8.0, 18.0)
    component += _clamp((barrel_rate - 6.0) * 1.35, -8.0, 18.0)
    component += _clamp((slugging - 0.380) * 45.0, -8.0, 16.0)
    component += _clamp((iso - 0.140) * 70.0, -8.0, 16.0)
    component -= _clamp((whiff_rate - 27.0) * 0.45, -6.0, 14.0)
    return component


def _severe_primary_weakness(profile: BatterPitchProfile, pitch: str) -> bool:
    return (
        _metric(profile.hr_rate_by_pitch_type, pitch) < 1.5
        and _metric(profile.barrel_rate_by_pitch_type, pitch) < 5.0
        and _metric(profile.slugging_by_pitch_type, pitch) < 0.340
        and _metric(profile.iso_by_pitch_type, pitch) < 0.115
    ) or (
        _metric(profile.whiff_rate_by_pitch_type, pitch) >= 36.0
        and _metric(profile.slugging_by_pitch_type, pitch) < 0.360
    )


def _has_batter_pitch_data(profile: BatterPitchProfile, pitch: str) -> bool:
    return any(
        _norm(pitch) in {_norm(key) for key in metric.keys()}
        for metric in [
            profile.hr_rate_by_pitch_type,
            profile.barrel_rate_by_pitch_type,
            profile.slugging_by_pitch_type,
            profile.iso_by_pitch_type,
            profile.whiff_rate_by_pitch_type,
        ]
    )


def _metric(values: dict[str, float], pitch: str) -> float:
    normalized = {_norm(key): float(value) for key, value in values.items()}
    return normalized.get(_norm(pitch), 0.0)


def _confidence(profile: PitchMixProfile, batter: BatterPitchProfile, matched_pitches: List[str]) -> float:
    available = 0
    available += 1 if profile.pitch_types else 0
    available += 1 if profile.pitch_usage_percentages else 0
    available += 1 if profile.primary_pitch else 0
    available += 1 if profile.secondary_pitch else 0
    available += min(3, len(matched_pitches))
    available += 1 if batter.hr_rate_by_pitch_type else 0
    available += 1 if batter.barrel_rate_by_pitch_type else 0
    available += 1 if batter.slugging_by_pitch_type else 0
    available += 1 if batter.iso_by_pitch_type else 0
    available += 1 if batter.whiff_rate_by_pitch_type else 0
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
    primary_pitch_collision: bool,
    severe_primary_weakness: bool,
    multiple_positive_collisions: bool,
    elite_pitch_type_specialist: bool,
) -> List[str]:
    notes: List[str] = []
    if primary_pitch_collision:
        notes.append("primary pitch collision")
    if multiple_positive_collisions:
        notes.append("multiple positive pitch-type collisions")
    if elite_pitch_type_specialist:
        notes.append("elite pitch-type specialist surfaced")
    if severe_primary_weakness:
        notes.append("severe primary pitch weakness")
    if not notes:
        notes.append("neutral pitch mix matchup")
    return notes


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
