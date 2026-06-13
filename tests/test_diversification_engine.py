from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.diversification import (
    DiversificationEngine,
    DiversificationProfile,
    DiversificationRecommendation,
    DiversificationResult,
    RiskTarget,
)
from russworks.explainability import ExplainabilityEngine
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.portfolio import PortfolioEngine
from russworks.slips import Slip, SlipLeg, SlipPortfolio

from tests.test_daily_pipeline import _slate


DATE = "2026-06-13"


def _slip(name: str, team: str, slip_type: str = "core", confidence_grade: str = "High") -> Slip:
    legs = [
        SlipLeg(f"{team} Batter 1", team, "A", "A", 88.0, "core", "test", confidence_score=82.0, confidence_grade=confidence_grade),
        SlipLeg(f"{team} Batter 2", team, "A", "A", 86.0, "core", "test", confidence_score=82.0, confidence_grade=confidence_grade),
    ]
    return Slip(
        name=name,
        slip_type=slip_type,
        legs=legs,
        justification="test slip",
        metadata={"team": team, "opponent": "KC", "cluster_strength": "elite"},
        confidence_score=82.0,
        confidence_grade=confidence_grade,
    )


def test_phase33_diversification_models_are_dataclasses():
    assert is_dataclass(DiversificationProfile)
    assert is_dataclass(DiversificationRecommendation)
    assert is_dataclass(DiversificationResult)


def test_diversification_engine_generates_targeted_swap_recommendations_and_exports_json():
    slips = SlipPortfolio(core_slips=[_slip("one", "TEX"), _slip("two", "TEX"), _slip("three", "TEX", confidence_grade="Low")])
    result = DiversificationEngine().analyze_diversification(slips, target=RiskTarget.CONSERVATIVE)

    assert result.target == RiskTarget.CONSERVATIVE
    assert result.recommendations
    assert result.suggested_swaps
    assert result.exposure_reduction_opportunities
    assert result.concentration_summary["team"]["TEX"] == 1.0

    with TemporaryDirectory() as temp_dir:
        output_path = DiversificationEngine().export_json(result, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "diversification_report.json"
    assert payload["target"] == "Conservative"


def test_diversification_engine_uses_portfolio_profile_when_supplied():
    slips = [_slip("one", "TEX"), _slip("two", "KC", "balanced"), _slip("three", "SEA", "chaos")]
    portfolio = PortfolioEngine().analyze_portfolio(slips)
    result = DiversificationEngine().analyze_diversification(slips, target="Aggressive", portfolio_profile=portfolio)

    assert result.target == RiskTarget.AGGRESSIVE
    assert result.recommendations
    assert result.diversified_portfolio_alternatives


def test_daily_pipeline_exports_diversification_report_and_full_report_section():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, request)

        assert result.success
        assert result.diversification_report is not None
        assert result.diversification_report_path == str(output_root.parent / "diversification" / "diversification_report.json")
        assert Path(result.diversification_report_path).exists()

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))
        assert payload["diversification"]["target"] == "Balanced"
        assert payload["explanations"]["diversification_context"]["target"] == "Balanced"


def test_command_center_dashboard_and_explainability_surface_diversification_context():
    result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))

    command_center = CommandCenterEngine().build_report(daily_run_result=result)
    dashboard = CalibrationDashboardEngine().build_dashboard(diversification_result=result.diversification_report)
    explanations = ExplainabilityEngine().generate_explanations(
        slip_portfolio=result.step5_result,
        portfolio_profile=result.portfolio_report,
        diversification_result=result.diversification_report,
    )

    assert command_center.formula_health.diversification_summary["target"] == "Balanced"
    assert result.diversification_report_path in command_center.execution_summary.exports_generated
    assert dashboard.diversification_summaries
    assert explanations["diversification_context"]["recommendations"]
