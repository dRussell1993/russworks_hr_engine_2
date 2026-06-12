from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from russworks.config.weights import ScoringWeights
from russworks.intake import BatterIntake, GameIntake, ReviewQueue, validate_step2_intake
from russworks.models import Batter, GameEnvironment, Pitcher, RussTier
from russworks.scoring.cps import ClusterParticipationInput, ClusterParticipationScore, calculate_cps
from russworks.scoring.environment import EnvironmentScore, EnvironmentScoreInput, calculate_environment_score
from russworks.scoring.lstm import LineupSlotTrendInput, calculate_lstm
from russworks.scoring.pvs import PitchVulnerabilityInput, calculate_pvs
from russworks.scoring.tag import TeamAttackGrade, TeamAttackGradeInput, calculate_tag
from russworks.scoring.umpire import UmpireScore, UmpireScoreInput, calculate_umpire_score
from russworks.scoring.weakspot import PitcherWeakSpotProfile, WeakSpotCollisionEngine, WeakSpotProfile

from .models import BatterReview, BatterReviewResult


@dataclass(frozen=True)
class Step3GameContext:
    game: GameIntake
    review_queue: ReviewQueue
    environment_score: EnvironmentScore
    umpire_score: UmpireScore
    tag_by_team: Dict[str, TeamAttackGrade]
    cps_by_team: Dict[str, ClusterParticipationScore]
    opponent_pitcher_by_team: Dict[str, Pitcher]


class Step3ReviewError(RuntimeError):
    pass


class Step3ReviewEngine:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights.defaults()
        self.weak_spot_collision_engine = WeakSpotCollisionEngine()

    def review_all_batters(self, game: GameIntake) -> BatterReviewResult:
        queue = validate_step2_intake(game)
        if not queue.is_valid:
            return BatterReviewResult(
                total_batters=queue.total_batters,
                reviewed_batters=0,
                reviews=[],
                errors=["Step 2 validation incomplete; Step 3 review blocked."],
                skipped_batters=[batter.name for batter in queue.review_required],
            )

        context = self._build_context(game, queue)
        reviews = [self.review_batter(batter, context) for batter in queue.review_required]
        reviewed_names = {review.batter_name for review in reviews}
        skipped = [batter.name for batter in queue.review_required if batter.name not in reviewed_names]
        errors = ["One or more batters were skipped during Step 3 review."] if skipped else []
        return BatterReviewResult(
            total_batters=queue.total_batters,
            reviewed_batters=len(reviews),
            reviews=reviews,
            errors=errors,
            skipped_batters=skipped,
        )

    def review_batter(self, batter: BatterIntake, game_context: Step3GameContext) -> BatterReview:
        game = game_context.game
        opponent_pitcher = game_context.opponent_pitcher_by_team[batter.team]
        batter_model = _to_batter_model(batter)
        pvs = calculate_pvs(
            PitchVulnerabilityInput(
                batter=batter_model,
                pitcher=opponent_pitcher,
                weak_spots=game.weak_spots,
                hr_matchups=game.hr_matchups,
                weights=self.weights,
            )
        )
        collision = self.weak_spot_collision_engine.score_collision(
            _batter_collision_profile(batter, opponent_pitcher.name, game),
            _pitcher_collision_profile(opponent_pitcher, game),
        )
        tag = game_context.tag_by_team[batter.team]
        cps = game_context.cps_by_team[batter.team]
        lstm = calculate_lstm(
            LineupSlotTrendInput(
                lineup_slot=batter.lineup_slot or 0,
                tag_grade=tag.grade,
                cps_grade=cps.grade,
                has_strong_pvs=pvs.label in {"strong", "elite"},
                has_environment_boost=game_context.environment_score.label in {"positive", "extreme"},
                weights=self.weights,
            )
        )

        ypi_flag = _has_any_tag(batter, {"ypi", "young", "prospect", "rookie", "small sample", "speed-power"})
        catcher_power_flag = _has_any_tag(batter, {"catcher"})
        veteran_bounce_flag = _has_any_tag(batter, {"veteran", "superstar", "5-tool", "power threat"})
        weak_spot_collision_flag = pvs.components.get("weak_spot_collision", 0.0) > 0 or collision.collision_score >= 25
        non_superstar_core_flag = not _has_any_tag(batter, {"superstar"}) and (
            pvs.label in {"strong", "elite"} or tag.grade.startswith("A") or cps.grade.startswith("A")
        )

        final_score = _final_russ_score(
            batter=batter,
            lstm_score=lstm.score,
            tag_score=tag.score,
            cps_score=cps.score,
            pvs_score=pvs.score,
            environment_score=game_context.environment_score.score,
            umpire_score=game_context.umpire_score.score,
            ypi_flag=ypi_flag,
            catcher_power_flag=catcher_power_flag,
            veteran_bounce_flag=veteran_bounce_flag,
            non_superstar_core_flag=non_superstar_core_flag,
        )
        return BatterReview(
            batter_name=batter.name,
            team=batter.team,
            opponent=opponent_pitcher.name,
            lineup_slot=batter.lineup_slot or 0,
            hr_pct=batter.hr_pct,
            lstm_score=lstm.score,
            tag_contribution=tag.score,
            cps_contribution=cps.score,
            pvs_contribution=pvs.score,
            environment_score=game_context.environment_score.score,
            umpire_score=game_context.umpire_score.score,
            ypi_flag=ypi_flag,
            catcher_power_flag=catcher_power_flag,
            veteran_bounce_flag=veteran_bounce_flag,
            non_superstar_core_flag=non_superstar_core_flag,
            weak_spot_collision_flag=weak_spot_collision_flag,
            final_russ_score=final_score,
            russ_tier=_tier(final_score),
            notes=_review_notes(ypi_flag, catcher_power_flag, veteran_bounce_flag, non_superstar_core_flag, weak_spot_collision_flag),
            weak_spot_collision_score=collision.collision_score,
            weak_spot_collision_confidence=collision.collision_confidence,
            weak_spot_collision_grade=collision.collision_grade,
        )

    def _build_context(self, game: GameIntake, queue: ReviewQueue) -> Step3GameContext:
        if game.environment is None:
            raise Step3ReviewError("Step 3 context requires environment data.")
        environment = _environment_with_umpire(game.environment, game)
        environment_score = calculate_environment_score(EnvironmentScoreInput(environment, weights=self.weights))
        umpire_score = calculate_umpire_score(UmpireScoreInput(environment.umpire, weights=self.weights))

        away_pitcher = _to_pitcher_model(game.away_team.starting_pitcher)
        home_pitcher = _to_pitcher_model(game.home_team.starting_pitcher)
        opponent_pitcher_by_team = {
            game.away_team.team: home_pitcher,
            game.home_team.team: away_pitcher,
        }

        tag_by_team: Dict[str, TeamAttackGrade] = {}
        cps_by_team: Dict[str, ClusterParticipationScore] = {}
        for team in game.teams:
            team_batters = [_to_batter_model(batter) for batter in team.batters]
            tag = calculate_tag(
                TeamAttackGradeInput(
                    team=team.team,
                    batters=team_batters,
                    opposing_pitcher=opponent_pitcher_by_team[team.team],
                    environment_score=environment_score.score,
                    umpire_score=umpire_score.score,
                    weights=self.weights,
                )
            )
            cps = calculate_cps(
                ClusterParticipationInput(
                    team=team.team,
                    batters=team_batters,
                    tag_score=tag.score,
                    environment_score=environment_score.score,
                    weights=self.weights,
                )
            )
            tag_by_team[team.team] = tag
            cps_by_team[team.team] = cps

        return Step3GameContext(
            game=game,
            review_queue=queue,
            environment_score=environment_score,
            umpire_score=umpire_score,
            tag_by_team=tag_by_team,
            cps_by_team=cps_by_team,
            opponent_pitcher_by_team=opponent_pitcher_by_team,
        )


def review_all_batters(game: GameIntake) -> BatterReviewResult:
    return Step3ReviewEngine().review_all_batters(game)


def review_batter(batter: BatterIntake, game_context: Step3GameContext) -> BatterReview:
    return Step3ReviewEngine().review_batter(batter, game_context)


def _to_batter_model(batter: BatterIntake) -> Batter:
    return Batter(
        name=batter.name,
        team=batter.team,
        bats=batter.bats,
        lineup_slot=batter.lineup_slot or 0,
        hr_pct=batter.hr_pct,
        pitch_mix_score=batter.pitch_mix_score,
        projected_ab=batter.projected_ab,
        projected_hits=batter.projected_hits,
        fair_odds=batter.fair_odds,
        book_odds=batter.book_odds,
        tags=list(batter.tags),
        confirmed=batter.confirmed,
    )


def _to_pitcher_model(pitcher) -> Pitcher:
    if pitcher is None:
        raise Step3ReviewError("Step 3 context requires pitcher data.")
    return Pitcher(
        name=pitcher.name,
        team=pitcher.team,
        throws=pitcher.throws,
        tags=list(pitcher.tags),
        projected_ip=pitcher.projected_ip,
        projected_hits=pitcher.projected_hits,
        projected_hr=pitcher.projected_hr,
        projected_bb=pitcher.projected_bb,
        projected_er=pitcher.projected_er,
        projected_outs=pitcher.projected_outs,
    )


def _environment_with_umpire(environment: GameEnvironment, game: GameIntake) -> GameEnvironment:
    if environment.umpire is not None:
        return environment
    return GameEnvironment(
        game_id=environment.game_id,
        date=environment.date,
        away_team=environment.away_team,
        home_team=environment.home_team,
        park=environment.park,
        temperature_f=environment.temperature_f,
        wind_mph=environment.wind_mph,
        wind_direction=environment.wind_direction,
        humidity_pct=environment.humidity_pct,
        roof=environment.roof,
        weather_hr_pct=environment.weather_hr_pct,
        weather_distance_ft=environment.weather_distance_ft,
        park_hr_factor=environment.park_hr_factor,
        umpire=game.umpire,
    )


def _batter_collision_profile(batter: BatterIntake, opponent_pitcher_name: str, game: GameIntake) -> WeakSpotProfile:
    matching_hr = [
        matchup
        for matchup in game.hr_matchups
        if matchup.batter_name.lower() == batter.name.lower()
        and matchup.pitcher_name.lower() == opponent_pitcher_name.lower()
    ]
    pitches = {matchup.pitch: matchup.matchup_score or batter.pitch_mix_score for matchup in matching_hr if matchup.pitch}
    zones = [matchup.notes for matchup in matching_hr if matchup.notes]
    return WeakSpotProfile(
        batter_name=batter.name,
        hot_zones=zones,
        barrel_zones=zones,
        pitch_type_performance=pitches or {"overall": batter.pitch_mix_score * 10.0},
    )


def _pitcher_collision_profile(pitcher: Pitcher, game: GameIntake) -> PitcherWeakSpotProfile:
    weak_spots = [weak_spot for weak_spot in game.weak_spots if weak_spot.pitcher_name.lower() == pitcher.name.lower()]
    weak_zones = [weak_spot.zone or weak_spot.pitch for weak_spot in weak_spots]
    attack_locations = [weak_spot.notes for weak_spot in weak_spots if weak_spot.notes] or weak_zones
    pitch_mix = {weak_spot.pitch: max(weak_spot.weakness_score * 10.0, 1.0) for weak_spot in weak_spots if weak_spot.pitch}
    if not pitch_mix:
        pitch_mix = {tag: 10.0 for tag in pitcher.tags}
    return PitcherWeakSpotProfile(
        pitcher_name=pitcher.name,
        weak_zones=weak_zones,
        pitch_mix=pitch_mix,
        attack_locations=attack_locations,
    )


def _has_any_tag(batter: BatterIntake, keys: set[str]) -> bool:
    tags = " ".join(batter.tags).lower()
    return any(key in tags for key in keys)


def _final_russ_score(
    *,
    batter: BatterIntake,
    lstm_score: float,
    tag_score: float,
    cps_score: float,
    pvs_score: float,
    environment_score: float,
    umpire_score: float,
    ypi_flag: bool,
    catcher_power_flag: bool,
    veteran_bounce_flag: bool,
    non_superstar_core_flag: bool,
) -> float:
    score = 35.0
    score += batter.hr_pct * 1.15
    score += lstm_score * 0.85
    score += (tag_score - 60.0) * 0.18
    score += (cps_score - 60.0) * 0.22
    score += pvs_score
    score += environment_score * 0.75
    score += umpire_score * 0.25
    score += 7.0 if ypi_flag else 0.0
    score += 7.0 if catcher_power_flag else 0.0
    score += 4.0 if veteran_bounce_flag else 0.0
    score += 3.0 if non_superstar_core_flag else 0.0
    if _has_any_tag(batter, {"superstar"}) and pvs_score < 5 and lstm_score < 10:
        score -= 3.0
    return round(max(20.0, min(score, 99.0)), 1)


def _tier(score: float) -> RussTier:
    if score >= 80:
        return RussTier.GOLD
    if score >= 70:
        return RussTier.SILVER
    if score >= 60:
        return RussTier.BRONZE
    return RussTier.NO


def _review_notes(
    ypi_flag: bool,
    catcher_power_flag: bool,
    veteran_bounce_flag: bool,
    non_superstar_core_flag: bool,
    weak_spot_collision_flag: bool,
) -> List[str]:
    notes = []
    if ypi_flag:
        notes.append("YPI")
    if catcher_power_flag:
        notes.append("Catcher Power")
    if veteran_bounce_flag:
        notes.append("Veteran Bounce")
    if non_superstar_core_flag:
        notes.append("Non-Superstar Core")
    if weak_spot_collision_flag:
        notes.append("Weak-Spot Collision")
    return notes
