from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.explainability import ExplainabilityEngine
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.portfolio import PortfolioEngine
from russworks.simulation import (
    MonteCarloEngine,
    PortfolioSimulation,
    SimulationResult,
    SimulationScenario,
    SimulationSummary,
)
from russworks.slips import Slip, SlipLeg, SlipPortfolio

from tests.test_daily_pipeline import _slate


DATE = "2026-06-13"


def _slip(name: str, team: str, slip_type: str = "core", confidence_grade: str = "High") -> Slip:
    legs = [
        SlipLeg(f"{team} Batter 1", team, "A", "A", 88.0, "core", "test", confidence_score=82.0, confidence_grade=confidence_grade),
        SlipLeg(f"{team} Batter 2", team, "A", "A", 84.0, "core", "test", confidence_score=78.0, confidence_grade=confidence_grade),
    ]
    return Slip(
        name=name,
        slip_type=slip_type,
        legs=legs,
        justification="test slip",
        metadata={"team": team, "opponent": "KC", "cluster_strength": "elite"},
        confidence_score=80.0,
        confidence_grade=confidence_grade,
    )


def test_phase34_simulation_models_are_dataclasses():
    assert is_dataclass(SimulationScenario)
    assert is_dataclass(PortfolioSimulation)
    assert is_dataclass(SimulationSummary)
    assert is_dataclass(SimulationResult)


def test_monte_carlo_engine_supports_required_simulation_counts_and_exports_json():
    slips = SlipPortfolio(core_slips=[_slip("core-one", "TEX"), _slip("core-two", "KC", "balanced")])
    engine = MonteCarloEngine()

    for count in [1000, 5000, 10000]:
        result = engine.simulate_portfolio(slips, scenario=SimulationScenario(simulation_count=count, random_seed=7))
        assert result.success
        assert result.summary.simulation_count == count
        assert 0.0 <= result.summary.expected_hit_rate <= 1.0
        assert result.summary.risk_grade.value in {"LOW", "MODERATE", "HIGH", "EXTREME"}
        assert result.portfolio_simulations

    with TemporaryDirectory() as temp_dir:
        output_path = engine.export_json(result, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "simulation_report.json"
    assert payload["summary"]["simulation_count"] == 10000


def test_monte_carlo_engine_uses_portfolio_exposure_and_rejects_invalid_counts():
    slips = [_slip("one", "TEX"), _slip("two", "TEX", "chaos", "Low")]
    portfolio = PortfolioEngine().analyze_portfolio(slips)

    result = MonteCarloEngine().simulate_portfolio(slips, portfolio_profile=portfolio)
    invalid = MonteCarloEngine().simulate_portfolio(slips, scenario=SimulationScenario(simulation_count=42))

    assert result.portfolio_exposure["team"]["TEX"] == 1.0
    assert result.summary.drawdown_risk >= 0.0
    assert not invalid.success
    assert "1000, 5000, or 10000" in invalid.errors[0]


def test_daily_pipeline_exports_simulation_report_and_full_report_section():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        request = DailyRunRequest(date=DATE, output_root=str(output_root))
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, request)

        assert result.success
        assert result.simulation_report is not None
        assert result.simulation_report_path == str(output_root.parent / "simulation" / "simulation_report.json")
        assert Path(result.simulation_report_path).exists()

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))
        assert payload["simulation"]["summary"]["simulation_count"] == 1000
        assert payload["explanations"]["simulation_context"]["simulation_count"] == 1000


def test_command_center_dashboard_and_explainability_surface_simulation_context():
    result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))

    command_center = CommandCenterEngine().build_report(daily_run_result=result)
    dashboard = CalibrationDashboardEngine().build_dashboard(simulation_result=result.simulation_report)
    explanations = ExplainabilityEngine().generate_explanations(
        slip_portfolio=result.step5_result,
        portfolio_profile=result.portfolio_report,
        diversification_result=result.diversification_report,
        simulation_result=result.simulation_report,
    )

    assert command_center.formula_health.simulation_summary["simulation_count"] == 1000
    assert result.simulation_report_path in command_center.execution_summary.exports_generated
    assert dashboard.simulation_summaries
    assert explanations["simulation_context"]["risk_grade"]
