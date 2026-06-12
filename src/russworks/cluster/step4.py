from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Dict, List, Sequence

from russworks.review import BatterReview, BatterReviewResult
from russworks.scoring.tag import grade_score

from .models import ClusterRanking, TeamClusterReport


_A_LEVEL_GRADES = {"A", "A+"}


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
        tag_grade = grade_score(tag_score)
        cps_grade = grade_score(cps_score)
        total_cluster_score = _cluster_score(reviews, tag_score, cps_score, tag_grade, cps_grade)
        ranked_batters = sorted(reviews, key=_batter_cluster_score, reverse=True)
        non_superstar = [review for review in ranked_batters if review.non_superstar_core_flag]
        catcher_power = [review for review in ranked_batters if review.catcher_power_flag]
        ypi = [review for review in ranked_batters if review.ypi_flag]
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
            batter_count=len(reviews),
            notes=_cluster_notes(tag_grade, cps_grade, reviews, total_cluster_score),
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
    special_depth = min(
        8.0,
        sum(
            1.5
            for review in reviews
            if review.non_superstar_core_flag or review.catcher_power_flag or review.ypi_flag
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
        + special_depth
        + elite_boost
    )
    return round(max(20.0, min(score, 100.0)), 2)


def _batter_cluster_score(review: BatterReview) -> float:
    score = review.final_russ_score * 0.55
    score += review.pvs_contribution * 1.10
    score += review.lstm_score * 0.45
    score += review.hr_pct * 0.35
    score += 5.0 if review.non_superstar_core_flag else 0.0
    score += 4.0 if review.weak_spot_collision_flag else 0.0
    score += 3.0 if review.ypi_flag else 0.0
    score += 3.0 if review.catcher_power_flag else 0.0
    return round(score, 2)


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
    if total_cluster_score >= 90:
        notes.append("Step 4 primary cluster candidate")
    return notes
