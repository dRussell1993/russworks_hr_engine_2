from __future__ import annotations

from dataclasses import asdict, is_dataclass
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping
import json

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.dashboard import CalibrationDashboard
from russworks.diversification import DiversificationResult
from russworks.portfolio import PortfolioProfile
from russworks.postmortem import PostMortemReport
from russworks.review import BatterReview, BatterReviewResult
from russworks.slips import Slip, SlipPortfolio

from .models import BatterExplanation, ExplanationFactor, SlipExplanation, TeamExplanation


class ExplainabilityEngine:
    def explain_batter_review(self, review: BatterReview) -> BatterExplanation:
        factors = [
            _factor("TAG contribution", review.tag_contribution, _impact(review.tag_contribution, 80, 65), "Team attack grade contribution from Step 3.", "BatterReview.tag_contribution"),
            _factor("CPS contribution", review.cps_contribution, _impact(review.cps_contribution, 80, 65), "Cluster participation contribution from Step 3.", "BatterReview.cps_contribution"),
            _factor("LSTM contribution", review.lstm_score, _impact(review.lstm_score, 10, 3), "Lineup slot multiplier contribution from Step 3.", "BatterReview.lstm_score"),
            _factor("PVS contribution", review.pvs_contribution, _impact(review.pvs_contribution, 12, 5), "Pitch vulnerability contribution from Step 3.", "BatterReview.pvs_contribution"),
            _factor("Environment contribution", review.environment_score, _impact(review.environment_score, 8, 1), "Weather and park environment contribution from Step 3.", "BatterReview.environment_score"),
            _factor("Umpire contribution", review.umpire_score, _impact(review.umpire_score, 2, 0.5), "Umpire run environment contribution from Step 3.", "BatterReview.umpire_score"),
            _factor("Weak Spot contribution", review.weak_spot_collision_score, _impact(review.weak_spot_collision_score, 45, 20), f"Weak-spot collision flag is {review.weak_spot_collision_flag}; grade {review.weak_spot_collision_grade}.", "BatterReview.weak_spot_collision_*"),
            _factor("Pitch Mix contribution", review.pitch_mix_matchup_score, _impact(review.pitch_mix_matchup_score, 65, 35), f"Pitch mix matchup grade {review.pitch_mix_matchup_grade}.", "BatterReview.pitch_mix_matchup_*"),
            _factor("Bullpen contribution", review.bullpen_exposure_score, _impact(review.bullpen_exposure_score, 65, 35), f"Bullpen exposure grade {review.bullpen_exposure_grade}.", "BatterReview.bullpen_exposure_*"),
            _factor("Park Factor contribution", review.park_factor_score, _impact(review.park_factor_score, 65, 35), f"Park factor grade {review.park_factor_grade}.", "BatterReview.park_factor_*"),
            _factor("YPI contribution", review.ypi_score, _impact(review.ypi_score, 65, 35), f"YPI flag is {review.ypi_flag}; grade {review.ypi_grade}.", "BatterReview.ypi_*"),
            _factor("Veteran Bounce contribution", review.veteran_bounce_score, _impact(review.veteran_bounce_score, 65, 35), f"Veteran Bounce flag is {review.veteran_bounce_flag}; grade {review.veteran_bounce_grade}.", "BatterReview.veteran_bounce_*"),
            _factor("Catcher Power contribution", review.catcher_power_score, _impact(review.catcher_power_score, 65, 35), f"Catcher Power flag is {review.catcher_power_flag}; grade {review.catcher_power_grade}.", "BatterReview.catcher_power_*"),
            _factor("Confidence", review.confidence_score, _impact(review.confidence_score, 78, 62), f"Confidence grade {review.confidence_grade}. {' '.join(review.confidence_reasoning)}", "BatterReview.confidence_*"),
        ]
        positive = [factor.name for factor in factors if factor.impact == "positive"]
        neutral = [factor.name for factor in factors if factor.impact == "neutral"]
        summary = (
            f"{review.batter_name} finished with Russ Score {review.final_russ_score} and tier {review.russ_tier.value}. "
            f"Positive drivers: {', '.join(positive) if positive else 'none'}. "
            f"Neutral or limited drivers: {', '.join(neutral) if neutral else 'none'}."
        )
        return BatterExplanation(batter=review.batter_name, team=review.team, summary=summary, factors=factors)

    def explain_team_ranking(self, report: TeamClusterReport, *, rank: int) -> TeamExplanation:
        drivers = [
            _factor("Team rank", rank, "context", f"{report.team} ranked #{rank} by total cluster score.", "ClusterRanking.ranked_teams order"),
            _factor("Total cluster score", report.total_cluster_score, _impact(report.total_cluster_score, 85, 70), "Primary Step 4 team ranking score.", "TeamClusterReport.total_cluster_score"),
            _factor("TAG grade", report.tag_grade, _grade_impact(report.tag_grade), "Team Attack Grade used as a primary cluster driver.", "TeamClusterReport.tag_grade"),
            _factor("CPS grade", report.cps_grade, _grade_impact(report.cps_grade), "Cluster Participation Score used as a primary cluster driver.", "TeamClusterReport.cps_grade"),
            _factor("Cluster captain", report.cluster_captain, "context", "Highest-ranked batter inside this team cluster.", "TeamClusterReport.cluster_captain"),
            _factor("Hidden beneficiary", report.hidden_cluster_beneficiary or "none", "context", "Non-obvious beneficiary identified by Step 4.", "TeamClusterReport.hidden_cluster_beneficiary"),
            _factor("Confidence", report.confidence_score, _impact(report.confidence_score, 78, 62), f"Team cluster confidence grade {report.confidence_grade}.", "TeamClusterReport.confidence_*"),
        ]
        cluster_drivers = [
            _count_factor("Core bats", report.core_bats, "TeamClusterReport.core_bats"),
            _count_factor("Secondary bats", report.secondary_bats, "TeamClusterReport.secondary_bats"),
            _count_factor("Non-superstar bats", report.non_superstar_cluster_bats, "TeamClusterReport.non_superstar_cluster_bats"),
            _count_factor("YPI bats", report.ypi_bats, "TeamClusterReport.ypi_bats"),
            _count_factor("Catcher Power bats", report.catcher_power_bats, "TeamClusterReport.catcher_power_bats"),
        ]
        concentration = _offensive_concentration(report)
        summary = (
            f"{report.team} ranked #{rank} with a {report.cluster_strength_label} cluster, "
            f"TAG {report.tag_grade}, CPS {report.cps_grade}, and score {report.total_cluster_score}."
        )
        return TeamExplanation(
            team=report.team,
            rank=rank,
            summary=summary,
            ranking_factors=drivers,
            cluster_drivers=cluster_drivers,
            offensive_concentration=concentration,
        )

    def explain_slip(self, slip: Slip) -> SlipExplanation:
        batter_reasons = {
            leg.batter: [
                _factor("Slip role", leg.slip_role, "context", leg.justification, "SlipLeg.slip_role"),
                _factor("TAG", leg.tag, _grade_impact(leg.tag), "Team TAG grade stored on the slip leg.", "SlipLeg.tag"),
                _factor("CPS", leg.cps, _grade_impact(leg.cps), "Team CPS grade stored on the slip leg.", "SlipLeg.cps"),
                _factor("Russ Score", leg.russ_score, _impact(leg.russ_score, 85, 70), "Russ/cluster score stored on the slip leg.", "SlipLeg.russ_score"),
                _factor("Confidence", leg.confidence_score, _impact(leg.confidence_score, 78, 62), f"Slip leg confidence grade {leg.confidence_grade}.", "SlipLeg.confidence_*"),
            ]
            for leg in slip.legs
        }
        archetype_factors = [
            _factor("Slip type", slip.slip_type, "context", _slip_type_summary(slip.slip_type), "Slip.slip_type"),
            _factor("Slip justification", slip.justification, "context", slip.justification, "Slip.justification"),
            _factor("Slip confidence", slip.confidence_score, _impact(slip.confidence_score, 78, 62), f"Slip confidence grade {slip.confidence_grade}.", "Slip.confidence_*"),
        ]
        validation_factors = [
            _factor("Unique batters", len(slip.batters) == len(set(slip.batters)), "positive" if len(slip.batters) == len(set(slip.batters)) else "negative", "Slip passed duplicate-batter validation when this is true.", "Slip.batters"),
            _factor("Leg justifications present", all(bool(leg.justification) for leg in slip.legs), "positive" if all(bool(leg.justification) for leg in slip.legs) else "negative", "Slip passed justification validation when every leg has justification text.", "SlipLeg.justification"),
            _factor("Slip justification present", bool(slip.justification), "positive" if slip.justification else "negative", "Slip passed justification validation when top-level justification is present.", "Slip.justification"),
        ]
        summary = (
            f"{slip.name} is a {slip.slip_type} slip with {len(slip.legs)} legs. "
            f"It was selected using stored leg roles, TAG/CPS labels, Russ scores, and validation metadata."
        )
        return SlipExplanation(
            slip_name=slip.name,
            slip_type=slip.slip_type,
            summary=summary,
            batter_selection_reasons=batter_reasons,
            archetype_factors=archetype_factors,
            validation_factors=validation_factors,
        )

    def generate_explanations(
        self,
        *,
        step3_results: BatterReviewResult | None = None,
        cluster_ranking: ClusterRanking | None = None,
        slip_portfolio: SlipPortfolio | None = None,
        dashboard: CalibrationDashboard | None = None,
        postmortem_report: PostMortemReport | None = None,
        command_center: Any | None = None,
        portfolio_profile: PortfolioProfile | None = None,
        diversification_result: DiversificationResult | None = None,
    ) -> dict[str, Any]:
        batter_explanations = [
            self.explain_batter_review(review).to_dict()
            for review in (step3_results.reviews if step3_results else [])
        ]
        team_explanations = [
            self.explain_team_ranking(report, rank=index).to_dict()
            for index, report in enumerate((cluster_ranking.ranked_teams if cluster_ranking else []), start=1)
        ]
        slip_explanations = [
            self.explain_slip(slip).to_dict()
            for slip in (slip_portfolio.all_slips if slip_portfolio else [])
        ]
        return {
            "batter_explanations": batter_explanations,
            "team_explanations": team_explanations,
            "slip_explanations": slip_explanations,
            "dashboard_context": _dashboard_context(dashboard),
            "postmortem_context": _postmortem_context(postmortem_report),
            "command_center_context": _command_center_context(command_center),
            "portfolio_context": _portfolio_context(portfolio_profile),
            "diversification_context": _diversification_context(diversification_result),
            "summaries": _summaries(batter_explanations, team_explanations, slip_explanations),
        }

    def export_json(self, explanations: Mapping[str, Any], output_dir: str | Path = "data/explanations") -> Path:
        output_path = Path(output_dir) / "explanations.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(_json_ready(dict(explanations)), indent=2, sort_keys=True), encoding="utf-8")
        return output_path


def generate_explanations(**kwargs: Any) -> dict[str, Any]:
    return ExplainabilityEngine().generate_explanations(**kwargs)


def _factor(name: str, value: Any, impact: str, summary: str, source: str) -> ExplanationFactor:
    return ExplanationFactor(name=name, value=value, impact=impact, summary=summary, source=source)


def _count_factor(name: str, values: list[str], source: str) -> ExplanationFactor:
    return _factor(name, len(values), "positive" if values else "neutral", f"{name}: {', '.join(values) if values else 'none'}.", source)


def _impact(value: float, positive_threshold: float, neutral_threshold: float) -> str:
    if value >= positive_threshold:
        return "positive"
    if value >= neutral_threshold:
        return "neutral"
    return "limited"


def _grade_impact(grade: str) -> str:
    if grade in {"A+", "A", "Elite", "Strong"}:
        return "positive"
    if grade in {"B", "Moderate", "Emerging", "Neutral"}:
        return "neutral"
    return "limited"


def _offensive_concentration(report: TeamClusterReport) -> str:
    if report.core_bats and report.non_superstar_cluster_bats:
        return f"{report.team} has concentrated power through core bats ({', '.join(report.core_bats)}) with non-superstar support ({', '.join(report.non_superstar_cluster_bats)})."
    if report.core_bats:
        return f"{report.team} concentration is led by core bats: {', '.join(report.core_bats)}."
    return f"{report.team} has no listed core bats in this cluster report."


def _slip_type_summary(slip_type: str) -> str:
    summaries = {
        "core": "Core slips are built around strongest TAG/CPS clusters.",
        "non_superstar_core": "Non-superstar core slips prioritize hidden/value bats surfaced by Step 4.",
        "balanced": "Balanced slips mix elite cluster bats and value bats.",
        "chaos": "Chaos slips allow higher-variance archetypes.",
        "contrarian": "Contrarian slips leverage overlooked clusters or lower-ownership paths.",
    }
    return summaries.get(slip_type, "Slip type explanation uses the stored slip_type field.")


def _dashboard_context(dashboard: CalibrationDashboard | None) -> dict[str, Any]:
    if dashboard is None:
        return {}
    return {
        "top_performing_modules": [module.module for module in dashboard.top_performing_modules],
        "worst_performing_modules": [module.module for module in dashboard.worst_performing_modules],
        "errors": list(dashboard.errors),
    }


def _postmortem_context(report: PostMortemReport | None) -> dict[str, Any]:
    if report is None:
        return {}
    return {
        "actual_home_runs": len(report.actual_home_runs),
        "winners": len(report.winner_log),
        "losers": len(report.loser_log),
        "false_positives": len(report.false_positive_log),
        "errors": list(report.errors),
    }


def _command_center_context(report: Any | None) -> dict[str, Any]:
    if report is None:
        return {}
    return {
        "success": report.success,
        "step2_status": report.execution_summary.step2_status,
        "step3_status": report.execution_summary.step3_status,
        "step4_status": report.execution_summary.step4_status,
        "step5_status": report.execution_summary.step5_status,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
    }


def _portfolio_context(profile: PortfolioProfile | None) -> dict[str, Any]:
    if profile is None:
        return {}
    return {
        "risk_grade": profile.risk_report.risk_grade.value,
        "risk_score": profile.risk_report.risk_score,
        "recommendations": [recommendation.message for recommendation in profile.recommendations],
        "team_exposure": dict(profile.exposure_report.team_exposure),
        "confidence_exposure": dict(profile.exposure_report.confidence_exposure),
    }


def _diversification_context(result: DiversificationResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "target": result.target.value,
        "recommendations": [recommendation.message for recommendation in result.recommendations],
        "suggested_swaps": list(result.suggested_swaps),
        "exposure_reduction_opportunities": list(result.exposure_reduction_opportunities),
        "diversified_portfolio_alternatives": list(result.diversified_portfolio_alternatives),
    }


def _summaries(batters: list[dict[str, Any]], teams: list[dict[str, Any]], slips: list[dict[str, Any]]) -> list[str]:
    return [
        f"Generated {len(batters)} Step 3 batter explanations.",
        f"Generated {len(teams)} Step 4 team explanations.",
        f"Generated {len(slips)} Step 5 slip explanations.",
    ]


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
