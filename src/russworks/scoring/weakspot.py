from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class WeakSpotProfile:
    batter_name: str
    hot_zones: Sequence[str] = ()
    barrel_zones: Sequence[str] = ()
    pitch_type_performance: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PitcherWeakSpotProfile:
    pitcher_name: str
    weak_zones: Sequence[str] = ()
    pitch_mix: Mapping[str, float] = field(default_factory=dict)
    attack_locations: Sequence[str] = ()


@dataclass(frozen=True)
class CollisionResult:
    collision_score: float
    collision_confidence: float
    collision_grade: str
    matched_zones: list[str] = field(default_factory=list)
    matched_pitches: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class WeakSpotCollisionEngine:
    def score_collision(
        self,
        batter_profile: WeakSpotProfile,
        pitcher_profile: PitcherWeakSpotProfile,
    ) -> CollisionResult:
        hot_zones = _normal_set(batter_profile.hot_zones)
        barrel_zones = _normal_set(batter_profile.barrel_zones)
        weak_zones = _normal_set(pitcher_profile.weak_zones)
        attack_locations = _normal_set(pitcher_profile.attack_locations)
        batter_pitches = _normal_mapping(batter_profile.pitch_type_performance)
        pitcher_mix = _normal_mapping(pitcher_profile.pitch_mix)

        direct_zone_matches = (hot_zones | barrel_zones) & weak_zones
        attack_zone_matches = (hot_zones | barrel_zones) & attack_locations
        barrel_weak_matches = barrel_zones & weak_zones
        matched_pitches = set(batter_pitches) & set(pitcher_mix)

        zone_component = len(direct_zone_matches) * 12.0
        attack_component = len(attack_zone_matches) * 5.0
        barrel_component = len(barrel_weak_matches) * 8.0
        pitch_component = _pitch_component(batter_pitches, pitcher_mix, matched_pitches)
        coverage_component = min(12.0, len(hot_zones | barrel_zones) * 1.5 + len(weak_zones | attack_locations) * 1.0)

        components = {
            "zone_overlap": round(zone_component, 2),
            "attack_location_overlap": round(attack_component, 2),
            "barrel_weak_zone_overlap": round(barrel_component, 2),
            "pitch_type_collision": round(pitch_component, 2),
            "profile_coverage": round(coverage_component, 2),
        }
        raw_score = sum(components.values())
        score = round(_clamp(raw_score, 0.0, 100.0), 2)
        confidence = _confidence(
            batter_profile=batter_profile,
            pitcher_profile=pitcher_profile,
            matched_zones=direct_zone_matches | attack_zone_matches,
            matched_pitches=matched_pitches,
        )
        notes = _notes(direct_zone_matches, attack_zone_matches, barrel_weak_matches, matched_pitches)
        return CollisionResult(
            collision_score=score,
            collision_confidence=confidence,
            collision_grade=_grade(score, confidence),
            matched_zones=sorted(direct_zone_matches | attack_zone_matches),
            matched_pitches=sorted(matched_pitches),
            components=components,
            notes=notes,
        )


def calculate_weak_spot_collision(
    batter_profile: WeakSpotProfile,
    pitcher_profile: PitcherWeakSpotProfile,
) -> CollisionResult:
    return WeakSpotCollisionEngine().score_collision(batter_profile, pitcher_profile)


def _normal_set(values: Sequence[str]) -> set[str]:
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _normal_mapping(values: Mapping[str, float]) -> dict[str, float]:
    return {str(key).strip().lower(): float(value) for key, value in values.items() if str(key).strip()}


def _pitch_component(
    batter_pitches: Mapping[str, float],
    pitcher_mix: Mapping[str, float],
    matched_pitches: set[str],
) -> float:
    component = 0.0
    for pitch in matched_pitches:
        batter_score = _clamp(float(batter_pitches[pitch]), 0.0, 100.0)
        mix_pct = _clamp(float(pitcher_mix[pitch]), 0.0, 100.0)
        component += (batter_score / 100.0) * (mix_pct / 100.0) * 45.0
    return component


def _confidence(
    *,
    batter_profile: WeakSpotProfile,
    pitcher_profile: PitcherWeakSpotProfile,
    matched_zones: set[str],
    matched_pitches: set[str],
) -> float:
    available_inputs = 0
    available_inputs += 1 if batter_profile.hot_zones else 0
    available_inputs += 1 if batter_profile.barrel_zones else 0
    available_inputs += 1 if batter_profile.pitch_type_performance else 0
    available_inputs += 1 if pitcher_profile.weak_zones else 0
    available_inputs += 1 if pitcher_profile.pitch_mix else 0
    available_inputs += 1 if pitcher_profile.attack_locations else 0
    base = available_inputs / 6.0
    match_bonus = min(0.25, len(matched_zones) * 0.05 + len(matched_pitches) * 0.05)
    return round(_clamp(base + match_bonus, 0.0, 1.0), 2)


def _grade(score: float, confidence: float) -> str:
    adjusted = score * (0.75 + confidence * 0.25)
    if adjusted >= 75:
        return "A+"
    if adjusted >= 60:
        return "A"
    if adjusted >= 42:
        return "B"
    if adjusted >= 25:
        return "C"
    return "D"


def _notes(
    direct_zone_matches: set[str],
    attack_zone_matches: set[str],
    barrel_weak_matches: set[str],
    matched_pitches: set[str],
) -> list[str]:
    notes: list[str] = []
    if direct_zone_matches:
        notes.append("batter hot/barrel zones overlap pitcher weak zones")
    if attack_zone_matches:
        notes.append("batter hot/barrel zones overlap pitcher attack locations")
    if barrel_weak_matches:
        notes.append("barrel zones collide with weak zones")
    if matched_pitches:
        notes.append("pitch type performance collides with pitcher mix")
    if not notes:
        notes.append("no meaningful weak-spot collision detected")
    return notes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))
