from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from russworks.slips import Slip, SlipPortfolio

from .models import ExposureReport, PortfolioProfile, PortfolioRecommendation, PortfolioRiskReport, RiskGrade


class PortfolioEngine:
    def analyze_portfolio(self, slips: SlipPortfolio | Sequence[Slip]) -> PortfolioProfile:
        slip_list = _slips(slips)
        exposure_report = self.generate_exposure_report(slip_list)
        risk_report = self.generate_risk_report(slip_list)
        return PortfolioProfile(
            generated_at=_now(),
            exposure_report=exposure_report,
            risk_report=risk_report,
            recommendations=list(risk_report.recommendations),
        )

    def generate_exposure_report(self, slips: SlipPortfolio | Sequence[Slip]) -> ExposureReport:
        slip_list = _slips(slips)
        total_slips = len(slip_list)
        legs = [leg for slip in slip_list for leg in slip.legs]
        total_legs = len(legs)
        return ExposureReport(
            total_slips=total_slips,
            total_legs=total_legs,
            team_exposure=_percentages(Counter(leg.team for leg in legs), total_legs),
            game_exposure=_percentages(Counter(_game_key(slip) for slip in slip_list), total_slips),
            batter_exposure=_percentages(Counter(leg.batter for leg in legs), total_legs),
            cluster_exposure=_percentages(Counter(_cluster_key(slip) for slip in slip_list), total_slips),
            confidence_exposure=_percentages(Counter(_confidence_bucket(slip) for slip in slip_list), total_slips),
            slip_archetype_exposure=_percentages(Counter(slip.slip_type for slip in slip_list), total_slips),
        )

    def generate_risk_report(self, slips: SlipPortfolio | Sequence[Slip]) -> PortfolioRiskReport:
        exposure = self.generate_exposure_report(slips)
        recommendations = _recommendations(exposure)
        risk_score = _risk_score(exposure)
        return PortfolioRiskReport(
            risk_grade=_risk_grade(risk_score),
            risk_score=risk_score,
            recommendations=recommendations,
            risk_factors=[recommendation.message for recommendation in recommendations],
        )

    def export_json(self, profile: PortfolioProfile, output_dir: str | Path = "data/portfolio") -> Path:
        output_path = Path(output_dir) / "portfolio_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(profile.to_json(), encoding="utf-8")
        return output_path


def analyze_portfolio(slips: SlipPortfolio | Sequence[Slip]) -> PortfolioProfile:
    return PortfolioEngine().analyze_portfolio(slips)


def generate_exposure_report(slips: SlipPortfolio | Sequence[Slip]) -> ExposureReport:
    return PortfolioEngine().generate_exposure_report(slips)


def generate_risk_report(slips: SlipPortfolio | Sequence[Slip]) -> PortfolioRiskReport:
    return PortfolioEngine().generate_risk_report(slips)


def _slips(slips: SlipPortfolio | Sequence[Slip]) -> list[Slip]:
    if isinstance(slips, SlipPortfolio):
        return list(slips.all_slips)
    return list(slips)


def _percentages(counter: Counter[str], total: int) -> dict[str, float]:
    if total <= 0:
        return {}
    return {key: round(count / total, 4) for key, count in sorted(counter.items()) if key}


def _game_key(slip: Slip) -> str:
    team = slip.metadata.get("team", "")
    opponent = slip.metadata.get("opponent", "")
    if not team and slip.legs:
        team = slip.legs[0].team
    if not opponent:
        opponent = "unknown"
    teams = sorted([team, opponent])
    return " vs ".join(team for team in teams if team)


def _cluster_key(slip: Slip) -> str:
    team = slip.metadata.get("team", slip.legs[0].team if slip.legs else "")
    strength = slip.metadata.get("cluster_strength", "unknown")
    return f"{team}:{strength}"


def _confidence_bucket(slip: Slip) -> str:
    grade = slip.confidence_grade or slip.metadata.get("confidence_grade", "Very Low")
    if grade in {"Elite", "High"}:
        return "high_confidence"
    if grade == "Medium":
        return "medium_confidence"
    return "low_confidence"


def _recommendations(exposure: ExposureReport) -> list[PortfolioRecommendation]:
    recommendations: list[PortfolioRecommendation] = []
    recommendations.extend(_concentration_recommendations("team_exposure", exposure.team_exposure, 0.50, "Reduce same-team exposure."))
    recommendations.extend(_concentration_recommendations("game_exposure", exposure.game_exposure, 0.60, "Reduce same-game exposure."))
    recommendations.extend(_concentration_recommendations("cluster_exposure", exposure.cluster_exposure, 0.45, "Reduce single-cluster concentration."))
    recommendations.extend(_concentration_recommendations("batter_exposure", exposure.batter_exposure, 0.35, "Reduce repeated batter exposure."))
    low_confidence = exposure.confidence_exposure.get("low_confidence", 0.0)
    if low_confidence > 0.35:
        recommendations.append(
            PortfolioRecommendation(
                category="confidence_exposure",
                risk_grade=_risk_grade(low_confidence * 100.0),
                message="Low-confidence slips are concentrated above the recommended threshold.",
                affected_items=["low_confidence"],
            )
        )
    recommendations.extend(_concentration_recommendations("slip_archetype_exposure", exposure.slip_archetype_exposure, 0.55, "Diversify slip archetype exposure."))
    if not recommendations:
        recommendations.append(
            PortfolioRecommendation(
                category="portfolio",
                risk_grade=RiskGrade.LOW,
                message="Portfolio exposure is balanced across teams, games, clusters, confidence levels, and slip archetypes.",
            )
        )
    return recommendations


def _concentration_recommendations(
    category: str,
    exposures: dict[str, float],
    threshold: float,
    message: str,
) -> list[PortfolioRecommendation]:
    affected = [item for item, value in exposures.items() if value > threshold]
    if not affected:
        return []
    max_exposure = max(exposures[item] for item in affected)
    return [
        PortfolioRecommendation(
            category=category,
            risk_grade=_risk_grade(max_exposure * 100.0),
            message=message,
            affected_items=affected,
        )
    ]


def _risk_score(exposure: ExposureReport) -> float:
    values = [
        max(exposure.team_exposure.values(), default=0.0),
        max(exposure.game_exposure.values(), default=0.0),
        max(exposure.cluster_exposure.values(), default=0.0),
        max(exposure.batter_exposure.values(), default=0.0),
        exposure.confidence_exposure.get("low_confidence", 0.0),
        max(exposure.slip_archetype_exposure.values(), default=0.0),
    ]
    return round(max(values, default=0.0) * 100.0, 1)


def _risk_grade(score: float) -> RiskGrade:
    if score >= 80.0:
        return RiskGrade.EXTREME
    if score >= 60.0:
        return RiskGrade.HIGH
    if score >= 40.0:
        return RiskGrade.MODERATE
    return RiskGrade.LOW


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
