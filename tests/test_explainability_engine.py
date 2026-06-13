from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.explainability import (
    BatterExplanation,
    ExplainabilityEngine,
    ExplanationFactor,
    SlipExplanation,
    TeamExplanation,
)
from russworks.models import RussTier
from russworks.review import BatterReview, BatterReviewResult
from russworks.slips import Slip, SlipLeg, SlipPortfolio


def _review() -> BatterReview:
    return BatterReview(
        batter_name="TEX Power",
        team="TEX",
        opponent="KC Starter",
        lineup_slot=4,
        hr_pct=14.0,
        lstm_score=15.0,
        tag_contribution=88.0,
        cps_contribution=84.0,
        pvs_contribution=16.0,
        environment_score=9.0,
        umpire_score=2.5,
        ypi_flag=True,
        catcher_power_flag=False,
        veteran_bounce_flag=True,
        non_superstar_core_flag=True,
        weak_spot_collision_flag=True,
        final_russ_score=91.0,
        russ_tier=RussTier.GOLD,
        weak_spot_collision_score=52.0,
        weak_spot_collision_confidence=0.78,
        weak_spot_collision_grade="A",
        ypi_score=72.0,
        ypi_confidence=0.70,
        ypi_grade="Strong",
        veteran_bounce_score=68.0,
        veteran_bounce_confidence=0.64,
        veteran_bounce_grade="Strong",
        catcher_power_score=0.0,
        catcher_power_confidence=0.0,
        catcher_power_grade="Weak",
        pitch_mix_matchup_score=70.0,
        pitch_mix_matchup_confidence=0.75,
        pitch_mix_matchup_grade="Strong",
        bullpen_exposure_score=66.0,
        bullpen_exposure_confidence=0.62,
        bullpen_exposure_grade="Strong",
        park_factor_score=64.0,
        park_factor_confidence=0.60,
        park_factor_grade="Moderate",
    )


def _team_report() -> TeamClusterReport:
    return TeamClusterReport(
        team="TEX",
        opponent="KC Starter",
        tag_grade="A+",
        cps_grade="A",
        total_cluster_score=94.5,
        cluster_strength_label="elite",
        cluster_captain="TEX Power",
        hidden_cluster_beneficiary="TEX Value",
        core_bats=["TEX Power", "TEX Value"],
        secondary_bats=["TEX Secondary"],
        non_superstar_cluster_bats=["TEX Value"],
        catcher_power_bats=[],
        ypi_bats=["TEX Value"],
        batter_count=9,
    )


def _slip() -> Slip:
    return Slip(
        name="TEX Core",
        slip_type="core",
        legs=[
            SlipLeg("TEX Power", "TEX", "A+", "A", 94.5, "core", "Cluster captain with elite TAG/CPS fit."),
            SlipLeg("TEX Value", "TEX", "A+", "A", 91.0, "value", "Hidden beneficiary in the same cluster."),
        ],
        justification="Core slip from strongest TAG/CPS cluster.",
        metadata={"team": "TEX", "cluster_score": "94.50"},
    )


def test_phase29_explainability_models_are_dataclasses():
    assert is_dataclass(ExplanationFactor)
    assert is_dataclass(BatterExplanation)
    assert is_dataclass(TeamExplanation)
    assert is_dataclass(SlipExplanation)


def test_batter_explanation_reflects_actual_step3_fields():
    explanation = ExplainabilityEngine().explain_batter_review(_review())

    assert explanation.batter == "TEX Power"
    assert "Russ Score 91.0" in explanation.summary
    factors = {factor.name: factor for factor in explanation.factors}

    assert factors["TAG contribution"].value == 88.0
    assert factors["PVS contribution"].value == 16.0
    assert factors["Weak Spot contribution"].value == 52.0
    assert factors["Catcher Power contribution"].impact == "limited"
    assert factors["Pitch Mix contribution"].source == "BatterReview.pitch_mix_matchup_*"


def test_team_explanation_uses_cluster_report_rank_and_concentration():
    explanation = ExplainabilityEngine().explain_team_ranking(_team_report(), rank=1)

    assert explanation.team == "TEX"
    assert explanation.rank == 1
    assert "TAG A+" in explanation.summary
    assert "non-superstar support" in explanation.offensive_concentration
    assert any(factor.name == "Total cluster score" and factor.value == 94.5 for factor in explanation.ranking_factors)


def test_slip_explanation_includes_selection_archetype_and_validation_factors():
    explanation = ExplainabilityEngine().explain_slip(_slip())

    assert explanation.slip_name == "TEX Core"
    assert explanation.batter_selection_reasons["TEX Power"][0].summary == "Cluster captain with elite TAG/CPS fit."
    assert explanation.archetype_factors[0].value == "core"
    assert all(factor.impact == "positive" for factor in explanation.validation_factors)


def test_generate_explanations_and_export_json():
    engine = ExplainabilityEngine()
    explanations = engine.generate_explanations(
        step3_results=BatterReviewResult(total_batters=1, reviewed_batters=1, reviews=[_review()]),
        cluster_ranking=ClusterRanking(total_teams=1, total_batters=1, ranked_teams=[_team_report()]),
        slip_portfolio=SlipPortfolio(core_slips=[_slip()]),
    )

    with TemporaryDirectory() as temp_dir:
        output_path = engine.export_json(explanations, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "explanations.json"
    assert len(payload["batter_explanations"]) == 1
    assert len(payload["team_explanations"]) == 1
    assert len(payload["slip_explanations"]) == 1
    assert "Generated 1 Step 5 slip explanations." in payload["summaries"]
