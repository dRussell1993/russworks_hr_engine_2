from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.explainability import ExplainabilityEngine
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.portfolio import (
    ExposureReport,
    PortfolioEngine,
    PortfolioProfile,
    PortfolioRecommendation,
    PortfolioRiskReport,
    RiskGrade,
)
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


def test_phase32_portfolio_models_are_dataclasses():
    assert is_dataclass(ExposureReport)
    assert is_dataclass(PortfolioRiskReport)
    assert is_dataclass(PortfolioRecommendation)
    assert is_dataclass(PortfolioProfile)


def test_portfolio_engine_flags_concentrated_exposure_and_exports_json():
    portfolio = SlipPortfolio(core_slips=[_slip("one", "TEX"), _slip("two", "TEX"), _slip("three", "TEX", confidence_grade="Low")])
    profile = PortfolioEngine().analyze_portfolio(portfolio)

    assert profile.risk_grade in {RiskGrade.HIGH, RiskGrade.EXTREME}
    assert profile.exposure_report.team_exposure["TEX"] == 1.0
    assert any(recommendation.category == "team_exposure" for recommendation in profile.recommendations)

    with TemporaryDirectory() as temp_dir:
        output_path = PortfolioEngine().export_json(profile, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "portfolio_report.json"
    assert payload["risk_report"]["risk_grade"] in {"HIGH", "EXTREME"}


def test_portfolio_engine_generates_balanced_recommendation_when_exposure_is_low():
    profile = PortfolioEngine().analyze_portfolio([_slip("one", "TEX", "core"), _slip("two", "KC", "balanced"), _slip("three", "SEA", "chaos")])

    assert profile.recommendations
    assert profile.recommendations[0].category in {"portfolio", "game_exposure", "slip_archetype_exposure"}


def test_daily_pipeline_exports_portfolio_report_and_full_report_section():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, request)

        assert result.success
        assert result.portfolio_report is not None
        assert result.portfolio_report_path == str(output_root.parent / "portfolio" / "portfolio_report.json")
        assert Path(result.portfolio_report_path).exists()

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))
        assert payload["portfolio"]["risk_report"]["risk_grade"] in {"LOW", "MODERATE", "HIGH", "EXTREME"}
        assert payload["explanations"]["portfolio_context"]["risk_grade"] in {"LOW", "MODERATE", "HIGH", "EXTREME"}


def test_command_center_dashboard_and_explainability_surface_portfolio_context():
    result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))

    command_center = CommandCenterEngine().build_report(daily_run_result=result)
    dashboard = CalibrationDashboardEngine().build_dashboard(portfolio_profile=result.portfolio_report)
    explanations = ExplainabilityEngine().generate_explanations(
        slip_portfolio=result.step5_result,
        portfolio_profile=result.portfolio_report,
    )

    assert command_center.formula_health.portfolio_risk_summary["risk_grade"] in {"LOW", "MODERATE", "HIGH", "EXTREME"}
    assert result.portfolio_report_path in command_center.execution_summary.exports_generated
    assert dashboard.portfolio_summaries
    assert explanations["portfolio_context"]["recommendations"]
