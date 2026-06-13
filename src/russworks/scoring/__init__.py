from __future__ import annotations

from statistics import mean
from typing import Dict, List, Tuple

from ..models import Batter, BatterScore, Game, Pitcher, RussTier, TeamClusterScore
from .bullpen import (
    BullpenExposureEngine,
    BullpenExposureResult,
    BullpenProfile,
    RelieverProfile,
    calculate_bullpen_exposure_score,
)
from .catcher import CatcherPowerEngine, CatcherPowerResult, CatcherProfile, calculate_catcher_power_score
from .cps import ClusterParticipationInput, ClusterParticipationScore, calculate_cps as calculate_cps_module
from .environment import EnvironmentScore, EnvironmentScoreInput, calculate_environment_score
from .lstm import LineupSlotTrendInput, LineupSlotTrendMultiplier, calculate_lstm
from .pitchmix import (
    BatterPitchProfile,
    PitchMixEngine,
    PitchMixMatchupResult,
    PitchMixProfile,
    calculate_pitch_mix_matchup_score,
)
from .pvs import PitchVulnerabilityInput, PitchVulnerabilityScore, calculate_pvs
from .tag import TeamAttackGrade, TeamAttackGradeInput, calculate_tag as calculate_tag_module, grade_score
from .umpire import UmpireScore, UmpireScoreInput, calculate_umpire_score
from .weakspot import (
    CollisionResult,
    PitcherWeakSpotProfile,
    WeakSpotCollisionEngine,
    WeakSpotProfile,
    calculate_weak_spot_collision,
)


def grade(score: float) -> str:
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


def tier(score: float) -> RussTier:
    if score >= 80:
        return RussTier.GOLD
    if score >= 70:
        return RussTier.SILVER
    if score >= 60:
        return RussTier.BRONZE
    return RussTier.NO


def calculate_lpas(slot: int, tag_grade: str = "B", cps_grade: str = "B") -> float:
    base = {
        1: 10,
        2: 5,
        3: 12,
        4: 15,
        5: 7,
        6: 0,
        7: -2,
        8: -6,
        9: -8,
    }.get(slot, -8)
    if slot == 7 and tag_grade.startswith("A") and cps_grade.startswith("A"):
        base = 8
    return float(base)


def environment_score(game: Game) -> float:
    env = game.environment
    score = 0.0
    score += max(min(env.weather_hr_pct / 4.0, 12), -8)
    score += max(min(env.weather_distance_ft / 3.0, 8), -6)
    if "coors" in env.park.lower():
        score += 10
    if "roof closed" in env.roof.lower() or env.roof.lower() == "closed":
        score -= 2
    if env.umpire:
        if "hot" in env.umpire.zone_type.lower():
            score += 2
        if "strict" in env.umpire.zone_type.lower() or "strike" in env.umpire.zone_type.lower():
            score -= 1
        if "generous" in env.umpire.zone_type.lower() or "walk" in env.umpire.zone_type.lower():
            score += 1
    return score


def pitcher_attackability(p: Pitcher) -> float:
    score = 50.0
    score += p.projected_hr * 14
    score += max(0, p.projected_hits - 4.5) * 2
    score += max(0, p.projected_bb - 1.5) * 2
    for tag in p.tags:
        t = tag.lower()
        if "hitter" in t or "meatball" in t or "struggling" in t or "short leash" in t or "small sample" in t:
            score += 5
        if "hr stingy" in t or "ground ball" in t or "ace" in t or "top of rotation" in t:
            score -= 6
        if "control issues" in t:
            score += 4
        if "swing" in t or "strikeout" in t or "k upside" in t:
            score -= 3
    return max(20, min(score, 90))


def calculate_ypi(b: Batter) -> float:
    tags = " ".join(b.tags).lower()
    score = 0.0
    if any(k in tags for k in ["ypi", "young", "prospect", "rookie", "small sample", "speed-power"]):
        score += 7
    if b.hr_pct >= 15 and any(k in tags for k in ["power", "speed", "everyday", "small sample"]):
        score += 4
    return score


def calculate_catcher_power(b: Batter) -> float:
    tags = " ".join(b.tags).lower()
    return 7.0 if "catcher" in tags or "c" == tags.strip() else 0.0


def calculate_veteran_bounce(b: Batter) -> float:
    tags = " ".join(b.tags).lower()
    if any(k in tags for k in ["veteran", "superstar", "5-tool", "power threat"]):
        return 4.0
    return 0.0


def calculate_chaos_cluster(b: Batter, team_tag: str, team_cps: str) -> float:
    tags = " ".join(b.tags).lower()
    score = 0.0
    if "small sample" in tags or "chaos" in tags or b.lineup_slot >= 7:
        score += 2
    if team_tag.startswith("A") and team_cps.startswith("A") and b.lineup_slot in {6, 7, 8, 9}:
        score += 4
    return score


def calculate_pitcher_collision(b: Batter, pitcher: Pitcher, game: Game) -> float:
    score = 0.0
    for hm in game.hr_matchups:
        if hm.batter_name.lower() == b.name.lower() and hm.pitcher_name.lower() == pitcher.name.lower():
            score += hm.matchup_score or 6
            if hm.exit_velo and hm.exit_velo >= 105:
                score += 4
            if hm.distance and hm.distance >= 400:
                score += 3
    if b.pitch_mix_score >= 7:
        score += 8
    elif b.pitch_mix_score >= 6:
        score += 5
    elif b.pitch_mix_score >= 5:
        score += 2
    elif b.pitch_mix_score and b.pitch_mix_score < 4:
        score -= 4
    return max(-8, min(score, 18))


def calculate_tag(team_batters: List[Batter], opponent_pitcher: Pitcher, game: Game) -> Tuple[float, str]:
    if not team_batters:
        return 0.0, "D"
    top5 = [b.hr_pct for b in team_batters if b.lineup_slot <= 5]
    all_hr = [b.hr_pct for b in team_batters]
    score = 45 + mean(all_hr) * 1.6 + mean(top5 or all_hr) * 1.3
    score += environment_score(game) * 0.8
    score += (pitcher_attackability(opponent_pitcher) - 50) * 0.6
    score += sum(1 for b in team_batters if b.hr_pct >= 15) * 2
    score = max(20, min(score, 100))
    return score, grade(score)


def calculate_cps(team_batters: List[Batter], tag_score: float, game: Game) -> Tuple[float, str, List[str]]:
    if not team_batters:
        return 0.0, "D", []
    sorted_batters = sorted(team_batters, key=lambda b: b.hr_pct, reverse=True)
    top = sorted_batters[:4]
    top_hr_sum = sum(b.hr_pct for b in top)
    top_slots = sum(1 for b in top if b.lineup_slot <= 5)
    viable = sum(1 for b in team_batters if b.hr_pct >= 12)
    score = 35 + top_hr_sum * 0.7 + top_slots * 4 + viable * 2 + (tag_score - 60) * 0.35
    score += environment_score(game) * 0.5
    score = max(20, min(score, 100))
    return score, grade(score), [b.name for b in top]


def opponent_pitcher_for_batter(game: Game, b: Batter) -> Pitcher:
    if b.team == game.environment.away_team:
        return game.home_pitcher
    return game.away_pitcher


def score_batter(game: Game, b: Batter, team_cluster: TeamClusterScore) -> BatterScore:
    pitcher = opponent_pitcher_for_batter(game, b)
    env_component = environment_score(game)
    lpas = calculate_lpas(b.lineup_slot, team_cluster.tag_grade, team_cluster.cps_grade)
    ypi = calculate_ypi(b)
    catcher = calculate_catcher_power(b)
    vet = calculate_veteran_bounce(b)
    chaos = calculate_chaos_cluster(b, team_cluster.tag_grade, team_cluster.cps_grade)
    collision = calculate_pitcher_collision(b, pitcher, game)
    pit = pitcher_attackability(pitcher)
    score = 35
    score += b.hr_pct * 1.15
    score += lpas * 0.85
    score += env_component * 0.75
    score += (team_cluster.tag_score - 60) * 0.18
    score += (team_cluster.cps_score - 60) * 0.22
    score += (pit - 50) * 0.25
    score += ypi + catcher + vet + chaos + collision
    if "superstar" in " ".join(b.tags).lower() and not (collision >= 5 or lpas >= 10):
        score -= 3
    score = max(20, min(score, 99))
    notes = []
    if ypi: notes.append("YPI")
    if catcher: notes.append("Catcher Power")
    if vet: notes.append("Veteran/Superstar")
    if collision >= 8: notes.append("Strong Collision")
    if team_cluster.cps_grade.startswith("A"): notes.append("CPS Boost")
    return BatterScore(
        batter=b,
        opponent_pitcher=pitcher,
        lpas=lpas,
        tag_component=team_cluster.tag_score,
        cps_component=team_cluster.cps_score,
        ypi=ypi,
        catcher_power=catcher,
        veteran_bounce=vet,
        chaos_cluster=chaos,
        pitcher_collision=collision,
        environment=env_component,
        final_score=round(score, 1),
        tier=tier(score),
        board=" / ".join(notes) if notes else "Standard",
        notes=notes,
    )


def calculate_team_clusters(game: Game) -> Dict[str, TeamClusterScore]:
    clusters: Dict[str, TeamClusterScore] = {}
    for team in [game.environment.away_team, game.environment.home_team]:
        team_batters = game.batters_for_team(team)
        opponent = game.home_pitcher if team == game.environment.away_team else game.away_pitcher
        tag_score, tag_grade = calculate_tag(team_batters, opponent, game)
        cps_score, cps_grade, core = calculate_cps(team_batters, tag_score, game)
        cluster_score = round((tag_score * 0.45) + (cps_score * 0.55), 1)
        clusters[team] = TeamClusterScore(
            team=team,
            tag_score=round(tag_score, 1),
            tag_grade=tag_grade,
            cps_score=round(cps_score, 1),
            cps_grade=cps_grade,
            cluster_score=cluster_score,
            core_batters=core,
            notes=[],
        )
    return clusters


def score_game(game: Game) -> List[BatterScore]:
    clusters = calculate_team_clusters(game)
    scores = []
    for b in sorted(game.batters, key=lambda x: (x.team, x.lineup_slot)):
        scores.append(score_batter(game, b, clusters[b.team]))
    return scores


__all__ = [
    "CatcherPowerEngine",
    "CatcherPowerResult",
    "CatcherProfile",
    "BatterPitchProfile",
    "BullpenExposureEngine",
    "BullpenExposureResult",
    "BullpenProfile",
    "ClusterParticipationInput",
    "ClusterParticipationScore",
    "CollisionResult",
    "EnvironmentScore",
    "EnvironmentScoreInput",
    "LineupSlotTrendInput",
    "LineupSlotTrendMultiplier",
    "PitchMixEngine",
    "PitchMixMatchupResult",
    "PitchMixProfile",
    "PitcherWeakSpotProfile",
    "PitchVulnerabilityInput",
    "PitchVulnerabilityScore",
    "RelieverProfile",
    "TeamAttackGrade",
    "TeamAttackGradeInput",
    "UmpireScore",
    "UmpireScoreInput",
    "WeakSpotCollisionEngine",
    "WeakSpotProfile",
    "calculate_bullpen_exposure_score",
    "calculate_catcher_power_score",
    "calculate_cps_module",
    "calculate_environment_score",
    "calculate_lstm",
    "calculate_pitch_mix_matchup_score",
    "calculate_pvs",
    "calculate_tag_module",
    "calculate_team_clusters",
    "calculate_umpire_score",
    "calculate_weak_spot_collision",
    "score_game",
]
