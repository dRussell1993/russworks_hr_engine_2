from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.confidence import ConfidenceBreakdown, ConfidenceEngine, ConfidenceProfile, ConfidenceResult
from russworks.dashboard import CalibrationDashboardEngine
from russworks.explainability import ExplainabilityEngine
from russworks.pipeline import DailyRunRequest, RussWorksPipeline

from tests.test_daily_pipeline import _slate


DATE = "2026-06-13"


def test_phase31_confidence_models_are_dataclasses():
    assert is_dataclass(ConfidenceBreakdown)
    assert is_dataclass(ConfidenceProfile)
    assert is_dataclass(ConfidenceResult)


def test_confidence_engine_scores_profiles_independently_from_russ_score():
    result = ConfidenceEngine().score_profile(
        ConfidenceProfile(
            subject="TEX Batter 1",
            subject_type="batter_review",
            breakdown=ConfidenceBreakdown(
                data_completeness=100.0,
                sample_size_quality=85.0,
                lineup_confirmation=100.0,
                integrity_warnings=90.0,
                environment_certainty=95.0,
                pitch_mix_certainty=80.0,
                weak_spot_certainty=75.0,
                bullpen_certainty=70.0,
                historical_consistency=65.0,
            ),
        )
    )

    assert result.confidence_score >= 80.0
    assert result.confidence_grade in {"High", "Elite"}
    assert result.confidence_reasoning
    assert result.breakdown.data_completeness == 100.0


def test_daily_pipeline_exports_confidence_on_reviews_clusters_and_slips():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, request)

        assert result.success
        review = result.step3_result.reviews[0]
        team_report = result.step4_result.ranked_teams[0]
        slip = result.step5_result.all_slips[0]

        assert review.confidence_score > 0.0
        assert review.confidence_grade in {"Elite", "High", "Medium", "Low", "Very Low"}
        assert "data_completeness" in review.confidence_breakdown
        assert team_report.confidence_score > 0.0
        assert team_report.confidence_grade in {"Elite", "High", "Medium", "Low", "Very Low"}
        assert slip.confidence_score == team_report.confidence_score
        assert slip.legs[0].confidence_grade == team_report.confidence_grade

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))
        first_review = payload["step3"]["batter_reviews"][0]
        first_slip = payload["step5"]["core_slips"][0]

        assert first_review["confidence"]["score"] > 0.0
        assert first_review["confidence"]["breakdown"]["lineup_confirmation"] == 100.0
        assert first_slip["confidence"]["grade"] in {"Elite", "High", "Medium", "Low", "Very Low"}
        assert first_slip["legs"][0]["confidence"]["score"] > 0.0


def test_explainability_includes_confidence_factors():
    result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))

    batter_explanation = ExplainabilityEngine().explain_batter_review(result.step3_result.reviews[0])
    team_explanation = ExplainabilityEngine().explain_team_ranking(result.step4_result.ranked_teams[0], rank=1)
    slip_explanation = ExplainabilityEngine().explain_slip(result.step5_result.all_slips[0])

    assert any(factor.name == "Confidence" for factor in batter_explanation.factors)
    assert any(factor.name == "Confidence" for factor in team_explanation.ranking_factors)
    assert any(factor.name == "Slip confidence" for factor in slip_explanation.archetype_factors)


def test_command_center_and_dashboard_surface_confidence_summaries():
    result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))
    command_center = CommandCenterEngine().build_report(daily_run_result=result)
    confidence_results = [
        ConfidenceEngine().result_from_fields(
            subject=review.batter_name,
            subject_type="batter_review",
            confidence_score=review.confidence_score,
            confidence_grade=review.confidence_grade,
            confidence_reasoning=review.confidence_reasoning,
            breakdown=review.confidence_breakdown,
        )
        for review in result.step3_result.reviews
    ]
    dashboard = CalibrationDashboardEngine().build_dashboard(confidence_results=confidence_results)

    assert command_center.formula_health.confidence_summary["average_confidence"] > 0.0
    assert command_center.formula_health.confidence_summary["grade_counts"]
    assert dashboard.confidence_summaries
