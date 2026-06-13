from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Dict, List, Sequence

from russworks.review import BatterReview, BatterReviewResult
from russworks.scoring.tag import grade_score

from .models import ClusterRanking, TeamClusterReport


_A_LEVEL_GRADES = {"A", "A+"}
_YPI_GRADE_RANK = {"Elite": 5, "Strong": 4, "Emerging": 3, "Neutral": 2, "Weak": 1}
_VETERAN_GRADE_RANK = {"Elite": 5, "Strong": 4, "Moderate": 3, "Neutral": 2, "Weak": 1}
_CATCHER_GRADE_RANK = {"Elite": 5, "Strong": 4, "Moderate": 3, "Neutral": 2, "Weak": 1}
_PITCH_MIX_GRADE_RANK = {"Elite": 5, "Strong": 4, "Moderate": 3, "Neutral": 2, "Weak": 1}
_BULLPEN_EXPOSURE_GRADE_RANK = {"Elite": 5, "Strong": 4, "Moderate": 3, "Neutral": 2, "Weak": 1}


class Step4ClusterEngine:
    def rank_team_clusters(self, step3_results: BatterReviewResult) -> ClusterRanking:
        validation_errors, missing_batters = self._validate_step3_results(step3_results)
        if validation_errors:
            return ClusterRanking(
                total_teams=0,
                total_batters=step3_results.reviewed_batters if step3_results else 0,
                ranked_teams=[],
                errors=validation_errors,
                missing_batters=missing_batters,
            )

        grouped = self._group_by_team(step3_results.reviews)
        grouped_batter_count = sum(len(reviews) for reviews in grouped.values())
        if grouped_batter_count != len(step3_results.reviews):
            return ClusterRanking(
                total_teams=len(grouped),
                total_batters=len(step3_results.reviews),
                ranked_teams=[],
                errors=["One or more Step 3 batters were missing from cluster evaluation."],
                missing_batters=self._missing_from_grouping(step3_results.reviews, grouped),
            )

        reports = [self.rank_cluster_batters(team, reviews) for team, reviews in grouped.items()]
        reports.sort(key=lambda report: report.total_cluster_score, reverse=True)
        return ClusterRanking(
            total_teams=len(reports),
            total_batters=len(step3_results.reviews),
            ranked_teams=reports,
            errors=[],
            missing_batters=[],
        )

    def rank_cluster_batters(self, team: str, batter_reviews: Sequence[BatterReview]) -> TeamClusterReport:
        reviews = list(batter_reviews)
        if not reviews:
            return TeamClusterReport(
                team=team,
                opponent="",
                tag_grade="D",
                cps_grade="D",
                total_cluster_score=0.0,
                cluster_strength_label="missing",
                cluster_captain="",
                hidden_cluster_beneficiary="",
                batter_count=0,
                notes=["no Step 3 batter reviews supplied"],
            )

        tag_score = mean(review.tag_contribution for review in reviews)
        cps_score = mean(review.cps_contribution for review in reviews)
        ypi_score = max(review.ypi_score for review in reviews)
        ypi_confidence = mean(review.ypi_confidence for review in reviews)
        ypi_grade = _top_ypi_grade(reviews)
        veteran_bounce_score = max(review.veteran_bounce_score for review in reviews)
        veteran_bounce_confidence = mean(review.veteran_bounce_confidence for review in reviews)
        veteran_bounce_grade = _top_veteran_bounce_grade(reviews)
        catcher_power_score = max(review.catcher_power_score for review in reviews)
        catcher_power_confidence = mean(review.catcher_power_confidence for review in reviews)
        catcher_power_grade = _top_catcher_power_grade(reviews)
        pitch_mix_matchup_score = max(review.pitch_mix_matchup_score for review in reviews)
        pitch_mix_matchup_confidence = mean(review.pitch_mix_matchup_confidence for review in reviews)
        pitch_mix_matchup_grade = _top_pitch_mix_matchup_grade(reviews)
        bullpen_exposure_score = max(review.bullpen_exposure_score for review in reviews)
        bullpen_exposure_confidence = mean(review.bullpen_exposure_confidence for review in reviews)
        bullpen_exposure_grade = _top_bullpen_exposure_grade(reviews)
        tag_grade = grade_score(tag_score)
        cps_grade = grade_score(cps_score)
        total_cluster_score = _cluster_score(reviews, tag_score, cps_score, tag_grade, cps_grade)
        ranked_batters = sorted(reviews, key=_batter_cluster_score, reverse=True)
        non_superstar = [review for review in ranked_batters if review.non_superstar_core_flag]
        catcher_power = [review for review in ranked_batters if review.catcher_power_flag]
        ypi = [review for review in ranked_batters if review.ypi_flag]
        veteran_bounce = [review for review in ranked_batters if review.veteran_bounce_flag]
        pitch_mix_matchup = [
            review
            for review in ranked_batters
            if review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"}
        ]
        bullpen_exposure = [
            review
            for review in ranked_batters
            if review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate"}
        ]
        core = ranked_batters[:4]
        secondary = ranked_batters[4:]
        captain = ranked_batters[0].batter_name
        hidden_beneficiary = _hidden_cluster_beneficiary(non_superstar, captain, secondary)

        return TeamClusterReport(
            team=team,
            opponent=_opponent_label(reviews),
            tag_grade=tag_grade,
            cps_grade=cps_grade,
            total_cluster_score=total_cluster_score,
            cluster_strength_label=_strength_label(total_cluster_score),
            cluster_captain=captain,
            hidden_cluster_beneficiary=hidden_beneficiary,
            core_bats=[review.batter_name for review in core],
            secondary_bats=[review.batter_name for review in secondary],
            non_superstar_cluster_bats=[review.batter_name for review in non_superstar],
            catcher_power_bats=[review.batter_name for review in catcher_power],
            ypi_bats=[review.batter_name for review in ypi],
            veteran_bounce_bats=[review.batter_name for review in veteran_bounce],
            pitch_mix_matchup_bats=[review.batter_name for review in pitch_mix_matchup],
            bullpen_exposure_bats=[review.batter_name for review in bullpen_exposure],
            batter_count=len(reviews),
            notes=_cluster_notes(
                tag_grade,
                cps_grade,
                reviews,
                total_cluster_score,
                ypi_grade,
                veteran_bounce_grade,
                catcher_power_grade,
                pitch_mix_matchup_grade,
                bullpen_exposure_grade,
            ),
            ypi_score=ypi_score,
            ypi_confidence=ypi_confidence,
            ypi_grade=ypi_grade,
            veteran_bounce_score=veteran_bounce_score,
            veteran_bounce_confidence=veteran_bounce_confidence,
            veteran_bounce_grade=veteran_bounce_grade,
            catcher_power_score=catcher_power_score,
            catcher_power_confidence=catcher_power_confidence,
            catcher_power_grade=catcher_power_grade,
            pitch_mix_matchup_score=pitch_mix_matchup_score,
            pitch_mix_matchup_confidence=pitch_mix_matchup_confidence,
            pitch_mix_matchup_grade=pitch_mix_matchup_grade,
            bullpen_exposure_score=bullpen_exposure_score,
            bullpen_exposure_confidence=bullpen_exposure_confidence,
            bullpen_exposure_grade=bullpen_exposure_grade,
        )

    def generate_cluster_report(self, step3_results: BatterReviewResult) -> ClusterRanking:
        return self.rank_team_clusters(step3_results)

    def _validate_step3_results(self, step3_results: BatterReviewResult | None) -> tuple[List[str], List[str]]:
        if step3_results is None:
            return ["Step 4 requires Step 3 results."], []
        errors: List[str] = []
        missing_batters: List[str] = []
        if not step3_results.reviews:
            errors.append("Step 4 requires Step 3 batter reviews before cluster ranking can run.")
        if not step3_results.success:
            errors.append("Step 4 blocked because Step 3 results are incomplete or contain errors.")
            missing_batters.extend(step3_results.skipped_batters)
        if step3_results.reviewed_batters != len(step3_results.reviews):
            errors.append("Step 3 reviewed batter count does not match supplied review rows.")
        if step3_results.total_batters != len(step3_results.reviews):
            errors.append("Not every Step 3 batter is present for Step 4 cluster evaluation.")
        return errors, sorted(set(missing_batters))

    def _group_by_team(self, reviews: Sequence[BatterReview]) -> Dict[str, List[BatterReview]]:
        grouped: Dict[str, List[BatterReview]] = defaultdict(list)
        for review in reviews:
            grouped[review.team].append(review)
        return dict(grouped)

    def _missing_from_grouping(
        self,
        reviews: Sequence[BatterReview],
        grouped: Dict[str, List[BatterReview]],
    ) -> List[str]:
        grouped_names = {review.batter_name for team_reviews in grouped.values() for review in team_reviews}
        return [review.batter_name for review in reviews if review.batter_name not in grouped_names]


def rank_team_clusters(step3_results: BatterReviewResult) -> ClusterRanking:
    return Step4ClusterEngine().rank_team_clusters(step3_results)


def rank_cluster_batters(team: str, batter_reviews: Sequence[BatterReview]) -> TeamClusterReport:
    return Step4ClusterEngine().rank_cluster_batters(team, batter_reviews)


def generate_cluster_report(step3_results: BatterReviewResult) -> ClusterRanking:
    return Step4ClusterEngine().generate_cluster_report(step3_results)


def _cluster_score(
    reviews: Sequence[BatterReview],
    tag_score: float,
    cps_score: float,
    tag_grade: str,
    cps_grade: str,
) -> float:
    avg_lstm = mean(review.lstm_score for review in reviews)
    avg_pvs = mean(review.pvs_contribution for review in reviews)
    avg_environment = mean(review.environment_score for review in reviews)
    avg_umpire = mean(review.umpire_score for review in reviews)
    avg_russ = mean(review.final_russ_score for review in reviews)
    max_ypi = max((review.ypi_score for review in reviews), default=0.0)
    max_veteran = max((review.veteran_bounce_score for review in reviews), default=0.0)
    max_catcher = max((review.catcher_power_score for review in reviews), default=0.0)
    max_pitch_mix = max((review.pitch_mix_matchup_score for review in reviews), default=0.0)
    max_bullpen = max((review.bullpen_exposure_score for review in reviews), default=0.0)
    special_depth = min(
        8.0,
        sum(
            1.5
            for review in reviews
            if review.non_superstar_core_flag
            or review.catcher_power_flag
            or review.ypi_flag
            or review.veteran_bounce_flag
            or review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"}
            or review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate"}
        ),
    )
    elite_boost = 6.0 if tag_grade in _A_LEVEL_GRADES and cps_grade in _A_LEVEL_GRADES else 0.0
    if not elite_boost and (tag_grade in _A_LEVEL_GRADES or cps_grade in _A_LEVEL_GRADES):
        elite_boost = 3.0

    score = (
        tag_score * 0.45
        + cps_score * 0.55
        + (avg_russ - 60.0) * 0.15
        + avg_pvs * 0.35
        + avg_lstm * 0.18
        + avg_environment * 0.25
        + avg_umpire * 0.10
        + max_ypi * 0.06
        + max_veteran * 0.05
        + max_catcher * 0.05
        + max_pitch_mix * 0.05
        + max_bullpen * 0.05
        + special_depth
        + elite_boost
    )
    return round(max(20.0, min(score, 100.0)), 2)


def _batter_cluster_score(review: BatterReview) -> float:
    score = review.final_russ_score * 0.55
    score += review.pvs_contribution * 1.10
    score += review.lstm_score * 0.45
    score += review.hr_pct * 0.35
    score += review.ypi_score * 0.12
    score += review.veteran_bounce_score * 0.10
    score += review.catcher_power_score * 0.10
    score += review.pitch_mix_matchup_score * 0.10
    score += review.bullpen_exposure_score * 0.10
    score += 5.0 if review.non_superstar_core_flag else 0.0
    score += 4.0 if review.weak_spot_collision_flag else 0.0
    score += 3.0 if review.ypi_flag else 0.0
    score += 3.0 if review.catcher_power_flag else 0.0
    score += 3.0 if review.veteran_bounce_flag else 0.0
    score += 3.0 if review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"} else 0.0
    score += 3.0 if review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate"} else 0.0
    return round(score, 2)


def _top_ypi_grade(reviews: Sequence[BatterReview]) -> str:
    return max((review.ypi_grade for review in reviews), key=lambda grade: _YPI_GRADE_RANK.get(grade, 0), default="Weak")


def _top_veteran_bounce_grade(reviews: Sequence[BatterReview]) -> str:
    return max((review.veteran_bounce_grade for review in reviews), key=lambda grade: _VETERAN_GRADE_RANK.get(grade, 0), default="Weak")


def _top_catcher_power_grade(reviews: Sequence[BatterReview]) -> str:
    return max((review.catcher_power_grade for review in reviews), key=lambda grade: _CATCHER_GRADE_RANK.get(grade, 0), default="Weak")


def _top_pitch_mix_matchup_grade(reviews: Sequence[BatterReview]) -> str:
    return max((review.pitch_mix_matchup_grade for review in reviews), key=lambda grade: _PITCH_MIX_GRADE_RANK.get(grade, 0), default="Weak")


def _top_bullpen_exposure_grade(reviews: Sequence[BatterReview]) -> str:
    return max((review.bullpen_exposure_grade for review in reviews), key=lambda grade: _BULLPEN_EXPOSURE_GRADE_RANK.get(grade, 0), default="Weak")


def _opponent_label(reviews: Sequence[BatterReview]) -> str:
    opponents = sorted({review.opponent for review in reviews if review.opponent})
    if not opponents:
        return ""
    if len(opponents) == 1:
        return opponents[0]
    return ", ".join(opponents)


def _hidden_cluster_beneficiary(
    non_superstar: Sequence[BatterReview],
    captain: str,
    secondary: Sequence[BatterReview],
) -> str:
    for review in non_superstar:
        if review.batter_name != captain:
            return review.batter_name
    for review in secondary:
        if review.batter_name != captain:
            return review.batter_name
    return ""


def _strength_label(score: float) -> str:
    if score >= 90:
        return "elite"
    if score >= 80:
        return "strong"
    if score >= 70:
        return "viable"
    if score >= 60:
        return "thin"
    return "weak"


def _cluster_notes(
    tag_grade: str,
    cps_grade: str,
    reviews: Sequence[BatterReview],
    total_cluster_score: float,
    ypi_grade: str,
    veteran_bounce_grade: str,
    catcher_power_grade: str,
    pitch_mix_matchup_grade: str,
    bullpen_exposure_grade: str,
) -> List[str]:
    notes: List[str] = []
    if tag_grade in _A_LEVEL_GRADES and cps_grade in _A_LEVEL_GRADES:
        notes.append("elite TAG/CPS cluster boost")
    elif tag_grade in _A_LEVEL_GRADES:
        notes.append("TAG-led cluster")
    elif cps_grade in _A_LEVEL_GRADES:
        notes.append("CPS-led cluster")
    if any(review.non_superstar_core_flag for review in reviews):
        notes.append("non-superstar core bats identified")
    if any(review.catcher_power_flag for review in reviews):
        notes.append("catcher power bats identified")
    if any(review.ypi_flag for review in reviews):
        notes.append("YPI bats identified")
    if any(review.veteran_bounce_flag for review in reviews):
        notes.append("Veteran Bounce bats identified")
    if any(review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"} for review in reviews):
        notes.append("Pitch Mix matchup bats identified")
    if any(review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate"} for review in reviews):
        notes.append("Bullpen Exposure bats identified")
    if ypi_grade in {"Elite", "Strong", "Emerging"}:
        notes.append(f"{ypi_grade} YPI cluster pressure")
    if veteran_bounce_grade in {"Elite", "Strong", "Moderate"}:
        notes.append(f"{veteran_bounce_grade} Veteran Bounce cluster pressure")
    if catcher_power_grade in {"Elite", "Strong", "Moderate"}:
        notes.append(f"{catcher_power_grade} Catcher Power cluster pressure")
    if pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"}:
        notes.append(f"{pitch_mix_matchup_grade} Pitch Mix cluster pressure")
    if bullpen_exposure_grade in {"Elite", "Strong", "Moderate"}:
        notes.append(f"{bullpen_exposure_grade} Bullpen Exposure cluster pressure")
    if total_cluster_score >= 90:
        notes.append("Step 4 primary cluster candidate")
    return notes
