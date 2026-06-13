from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from russworks.portfolio import ExposureReport, PortfolioEngine, PortfolioProfile
from russworks.slips import Slip, SlipPortfolio

from .models import DiversificationProfile, DiversificationRecommendation, DiversificationResult, RiskTarget


_TARGETS = {
    RiskTarget.CONSERVATIVE: DiversificationProfile(
        target=RiskTarget.CONSERVATIVE,
        team_threshold=0.30,
        game_threshold=0.40,
        cluster_threshold=0.30,
        confidence_threshold=0.20,
        archetype_threshold=0.35,
    ),
    RiskTarget.BALANCED: DiversificationProfile(),
    RiskTarget.AGGRESSIVE: DiversificationProfile(
        target=RiskTarget.AGGRESSIVE,
        team_threshold=0.55,
        game_threshold=0.65,
        cluster_threshold=0.50,
        confidence_threshold=0.45,
        archetype_threshold=0.60,
    ),
}


class DiversificationEngine:
    def analyze_diversification(
        self,
        slips: SlipPortfolio | Sequence[Slip],
        *,
        target: RiskTarget | str = RiskTarget.BALANCED,
        portfolio_profile: PortfolioProfile | None = None,
    ) -> DiversificationResult:
        risk_target = _target(target)
        profile = _TARGETS[risk_target]
        slip_list = _slips(slips)
        portfolio = portfolio_profile or PortfolioEngine().analyze_portfolio(slip_list)
        exposure = portfolio.exposure_report
        recommendations = [
            *self._recommend_for_exposure("team_concentration", risk_target, exposure.team_exposure, profile.team_threshold, slip_list),
            *self._recommend_for_exposure("game_concentration", risk_target, exposure.game_exposure, profile.game_threshold, slip_list),
            *self._recommend_for_exposure("cluster_concentration", risk_target, exposure.cluster_exposure, profile.cluster_threshold, slip_list),
            *self._recommend_for_exposure("archetype_concentration", risk_target, exposure.slip_archetype_exposure, profile.archetype_threshold, slip_list),
            *self._confidence_recommendations(risk_target, exposure, profile, slip_list),
        ]
        if not recommendations:
            recommendations.append(
                DiversificationRecommendation(
                    category="portfolio",
                    target=risk_target,
                    message=f"Portfolio already fits the {risk_target.value} diversification target.",
                    diversified_alternatives=["Maintain current spread; no forced swap recommended."],
                )
            )
        return DiversificationResult(
            generated_at=_now(),
            target=risk_target,
            recommendations=recommendations,
            suggested_swaps=[item for recommendation in recommendations for item in recommendation.suggested_swaps],
            exposure_reduction_opportunities=[item for recommendation in recommendations for item in recommendation.exposure_reduction_opportunities],
            diversified_portfolio_alternatives=[item for recommendation in recommendations for item in recommendation.diversified_alternatives],
            concentration_summary={
                "team": dict(exposure.team_exposure),
                "game": dict(exposure.game_exposure),
                "cluster": dict(exposure.cluster_exposure),
                "confidence": dict(exposure.confidence_exposure),
                "archetype": dict(exposure.slip_archetype_exposure),
            },
        )

    def _recommend_for_exposure(
        self,
        category: str,
        target: RiskTarget,
        exposures: dict[str, float],
        threshold: float,
        slips: Sequence[Slip],
    ) -> list[DiversificationRecommendation]:
        overexposed = [name for name, value in exposures.items() if value > threshold]
        if not overexposed:
            return []
        alternatives = _underexposed_candidates(exposures, threshold)
        return [
            DiversificationRecommendation(
                category=category,
                target=target,
                message=f"{category.replace('_', ' ').title()} exceeds {target.value} target for: {', '.join(overexposed)}.",
                suggested_swaps=_swap_suggestions(category, overexposed, alternatives, slips),
                exposure_reduction_opportunities=[f"Reduce {item} exposure from {exposures[item]:.1%} toward {threshold:.1%}." for item in overexposed],
                diversified_alternatives=alternatives or ["Add exposure to a different team/game/cluster/archetype bucket."],
            )
        ]

    def _confidence_recommendations(
        self,
        target: RiskTarget,
        exposure: ExposureReport,
        profile: DiversificationProfile,
        slips: Sequence[Slip],
    ) -> list[DiversificationRecommendation]:
        low_confidence = exposure.confidence_exposure.get("low_confidence", 0.0)
        if low_confidence <= profile.confidence_threshold:
            return []
        high_confidence_slips = [slip.name for slip in slips if _confidence_bucket(slip) == "high_confidence"]
        return [
            DiversificationRecommendation(
                category="confidence_concentration",
                target=target,
                message=f"Low-confidence concentration {low_confidence:.1%} exceeds {target.value} target {profile.confidence_threshold:.1%}.",
                suggested_swaps=[f"Replace one low-confidence slip with {name}." for name in high_confidence_slips[:3]],
                exposure_reduction_opportunities=["Reduce low-confidence concentration before adding more chaos or contrarian exposure."],
                diversified_alternatives=high_confidence_slips[:3] or ["Add a higher-confidence slip alternative."],
            )
        ]

    def export_json(self, result: DiversificationResult, output_dir: str | Path = "data/diversification") -> Path:
        output_path = Path(output_dir) / "diversification_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.to_json(), encoding="utf-8")
        return output_path


def analyze_diversification(
    slips: SlipPortfolio | Sequence[Slip],
    *,
    target: RiskTarget | str = RiskTarget.BALANCED,
    portfolio_profile: PortfolioProfile | None = None,
) -> DiversificationResult:
    return DiversificationEngine().analyze_diversification(slips, target=target, portfolio_profile=portfolio_profile)


def _slips(slips: SlipPortfolio | Sequence[Slip]) -> list[Slip]:
    if isinstance(slips, SlipPortfolio):
        return list(slips.all_slips)
    return list(slips)


def _target(value: RiskTarget | str) -> RiskTarget:
    if isinstance(value, RiskTarget):
        return value
    normalized = str(value).strip().lower()
    for target in RiskTarget:
        if target.value.lower() == normalized:
            return target
    return RiskTarget.BALANCED


def _underexposed_candidates(exposures: dict[str, float], threshold: float) -> list[str]:
    return [name for name, value in sorted(exposures.items(), key=lambda item: item[1]) if value < threshold]


def _swap_suggestions(category: str, overexposed: list[str], alternatives: list[str], slips: Sequence[Slip]) -> list[str]:
    suggestions: list[str] = []
    for name in overexposed:
        source_slip = _first_matching_slip(category, name, slips)
        target = alternatives[0] if alternatives else "an underexposed alternative"
        if source_slip:
            suggestions.append(f"Consider swapping exposure away from {source_slip} ({name}) toward {target}.")
        else:
            suggestions.append(f"Consider reducing {name} exposure toward {target}.")
    return suggestions


def _first_matching_slip(category: str, name: str, slips: Sequence[Slip]) -> str:
    for slip in slips:
        if category == "team_concentration" and any(leg.team == name for leg in slip.legs):
            return slip.name
        if category == "game_concentration" and _game_key(slip) == name:
            return slip.name
        if category == "cluster_concentration" and _cluster_key(slip) == name:
            return slip.name
        if category == "archetype_concentration" and slip.slip_type == name:
            return slip.name
    return ""


def _game_key(slip: Slip) -> str:
    team = slip.metadata.get("team", slip.legs[0].team if slip.legs else "")
    opponent = slip.metadata.get("opponent", "unknown")
    return " vs ".join(sorted(team for team in [team, opponent] if team))


def _cluster_key(slip: Slip) -> str:
    team = slip.metadata.get("team", slip.legs[0].team if slip.legs else "")
    return f"{team}:{slip.metadata.get('cluster_strength', 'unknown')}"


def _confidence_bucket(slip: Slip) -> str:
    if slip.confidence_grade in {"Elite", "High"}:
        return "high_confidence"
    if slip.confidence_grade == "Medium":
        return "medium_confidence"
    return "low_confidence"


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
