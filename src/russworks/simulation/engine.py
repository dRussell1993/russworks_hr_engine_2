from __future__ import annotations

from datetime import datetime
from math import sqrt
from pathlib import Path
import random
from typing import Sequence

from russworks.backtesting import BacktestResult, BacktestSummary
from russworks.portfolio import PortfolioEngine, PortfolioProfile
from russworks.slips import Slip, SlipPortfolio

from .models import (
    PortfolioSimulation,
    SimulationResult,
    SimulationRiskGrade,
    SimulationScenario,
    SimulationSummary,
)


SUPPORTED_SIMULATION_COUNTS = {1000, 5000, 10000}


class MonteCarloEngine:
    def simulate_portfolio(
        self,
        slips: SlipPortfolio | Sequence[Slip],
        *,
        scenario: SimulationScenario | None = None,
        portfolio_profile: PortfolioProfile | None = None,
        backtest_summary: BacktestSummary | BacktestResult | None = None,
    ) -> SimulationResult:
        active_scenario = scenario or SimulationScenario()
        slip_list = _slips(slips)
        if active_scenario.simulation_count not in SUPPORTED_SIMULATION_COUNTS:
            return SimulationResult(
                generated_at=_now(),
                scenario=active_scenario,
                errors=[
                    "Simulation count must be one of 1000, 5000, or 10000.",
                ],
            )
        if not slip_list:
            return SimulationResult(
                generated_at=_now(),
                scenario=active_scenario,
                summary=_empty_summary(active_scenario),
                errors=["Monte Carlo simulation requires at least one slip."],
            )

        portfolio = portfolio_profile or PortfolioEngine().analyze_portfolio(slip_list)
        historical_hit_rate = _historical_hit_rate(active_scenario, backtest_summary)
        portfolio_simulations = [_portfolio_simulation(slip, historical_hit_rate) for slip in slip_list]
        hit_rates, roi_values = _run_simulations(portfolio_simulations, active_scenario)
        summary = _summary(active_scenario, hit_rates, roi_values, portfolio.risk_report.risk_score)
        return SimulationResult(
            generated_at=_now(),
            scenario=active_scenario,
            portfolio_simulations=portfolio_simulations,
            summary=summary,
            portfolio_exposure={
                "team": dict(portfolio.exposure_report.team_exposure),
                "game": dict(portfolio.exposure_report.game_exposure),
                "cluster": dict(portfolio.exposure_report.cluster_exposure),
                "confidence": dict(portfolio.exposure_report.confidence_exposure),
                "archetype": dict(portfolio.exposure_report.slip_archetype_exposure),
            },
            notes=[
                "Simulation is advisory only and does not modify slips, scores, or formula weights.",
                f"Historical hit rate input: {historical_hit_rate:.1%}.",
            ],
        )

    def export_json(self, result: SimulationResult, output_dir: str | Path = "data/simulation") -> Path:
        output_path = Path(output_dir) / "simulation_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.to_json(), encoding="utf-8")
        return output_path


def simulate_portfolio(
    slips: SlipPortfolio | Sequence[Slip],
    *,
    scenario: SimulationScenario | None = None,
    portfolio_profile: PortfolioProfile | None = None,
    backtest_summary: BacktestSummary | BacktestResult | None = None,
) -> SimulationResult:
    return MonteCarloEngine().simulate_portfolio(
        slips,
        scenario=scenario,
        portfolio_profile=portfolio_profile,
        backtest_summary=backtest_summary,
    )


def _slips(slips: SlipPortfolio | Sequence[Slip]) -> list[Slip]:
    if isinstance(slips, SlipPortfolio):
        return list(slips.all_slips)
    return list(slips)


def _historical_hit_rate(
    scenario: SimulationScenario,
    backtest_summary: BacktestSummary | BacktestResult | None,
) -> float:
    if scenario.historical_hit_rate is not None:
        return _clamp(scenario.historical_hit_rate, 0.0, 1.0)
    summary = backtest_summary.summary if isinstance(backtest_summary, BacktestResult) else backtest_summary
    if summary is not None:
        return _clamp(summary.step5_hit_rate, 0.0, 1.0)
    return 0.08


def _portfolio_simulation(slip: Slip, historical_hit_rate: float) -> PortfolioSimulation:
    leg_probabilities = [_leg_probability(leg.russ_score, leg.confidence_score, historical_hit_rate) for leg in slip.legs]
    hit_probability = 1.0
    for probability in leg_probabilities:
        hit_probability *= probability
    average_russ = _average([leg.russ_score for leg in slip.legs])
    average_confidence = _average([leg.confidence_score for leg in slip.legs])
    team_counts: dict[str, int] = {}
    for leg in slip.legs:
        team_counts[leg.team] = team_counts.get(leg.team, 0) + 1
    total_legs = max(len(slip.legs), 1)
    return PortfolioSimulation(
        slip_name=slip.name,
        slip_type=slip.slip_type,
        legs=len(slip.legs),
        hit_probability=round(_clamp(hit_probability, 0.0, 1.0), 6),
        average_russ_score=round(average_russ, 2),
        average_confidence_score=round(average_confidence, 2),
        team_exposure={team: round(count / total_legs, 4) for team, count in sorted(team_counts.items())},
    )


def _leg_probability(russ_score: float, confidence_score: float, historical_hit_rate: float) -> float:
    score_probability = _clamp(russ_score / 100.0, 0.0, 1.0) * 0.25
    confidence_probability = _clamp(confidence_score / 100.0, 0.0, 1.0) * 0.20
    blended = score_probability * 0.55 + confidence_probability * 0.25 + historical_hit_rate * 0.20
    return _clamp(blended, 0.005, 0.45)


def _run_simulations(
    portfolio_simulations: Sequence[PortfolioSimulation],
    scenario: SimulationScenario,
) -> tuple[list[float], list[float]]:
    rng = random.Random(scenario.random_seed)
    hit_rates: list[float] = []
    roi_values: list[float] = []
    total_stake = max(len(portfolio_simulations) * scenario.stake_per_slip, 0.0001)
    for _ in range(scenario.simulation_count):
        hits = 0
        profit = 0.0
        for slip in portfolio_simulations:
            if rng.random() <= slip.hit_probability:
                hits += 1
                profit += scenario.stake_per_slip * max(scenario.payout_multiplier - 1.0, 0.0)
            else:
                profit -= scenario.stake_per_slip
        hit_rates.append(hits / len(portfolio_simulations))
        roi_values.append(profit / total_stake)
    return hit_rates, roi_values


def _summary(
    scenario: SimulationScenario,
    hit_rates: Sequence[float],
    roi_values: Sequence[float],
    portfolio_risk_score: float,
) -> SimulationSummary:
    expected_roi = _average(roi_values)
    volatility = _standard_deviation(roi_values)
    drawdown_risk = len([value for value in roi_values if value <= -0.50]) / max(len(roi_values), 1)
    variance = _variance(roi_values)
    risk_score = min(100.0, portfolio_risk_score * 0.35 + volatility * 45.0 + drawdown_risk * 100.0 * 0.35)
    return SimulationSummary(
        simulation_count=scenario.simulation_count,
        expected_hit_rate=round(_average(hit_rates), 4),
        expected_roi=round(expected_roi, 4),
        expected_variance=round(variance, 6),
        drawdown_risk=round(drawdown_risk, 4),
        portfolio_volatility=round(volatility, 4),
        confidence_intervals={
            "hit_rate": _confidence_interval(hit_rates),
            "roi": _confidence_interval(roi_values),
        },
        risk_grade=_risk_grade(risk_score),
    )


def _confidence_interval(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"p05": 0.0, "p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    return {
        "p05": round(_percentile(ordered, 0.05), 4),
        "p50": round(_percentile(ordered, 0.50), 4),
        "p95": round(_percentile(ordered, 0.95), 4),
    }


def _percentile(ordered_values: Sequence[float], percentile: float) -> float:
    if not ordered_values:
        return 0.0
    index = min(len(ordered_values) - 1, max(0, int(round((len(ordered_values) - 1) * percentile))))
    return ordered_values[index]


def _empty_summary(scenario: SimulationScenario) -> SimulationSummary:
    return SimulationSummary(
        simulation_count=scenario.simulation_count,
        expected_hit_rate=0.0,
        expected_roi=0.0,
        expected_variance=0.0,
        drawdown_risk=0.0,
        portfolio_volatility=0.0,
        confidence_intervals={"hit_rate": {"p05": 0.0, "p50": 0.0, "p95": 0.0}, "roi": {"p05": 0.0, "p50": 0.0, "p95": 0.0}},
        risk_grade=SimulationRiskGrade.LOW,
    )


def _risk_grade(score: float) -> SimulationRiskGrade:
    if score >= 80.0:
        return SimulationRiskGrade.EXTREME
    if score >= 60.0:
        return SimulationRiskGrade.HIGH
    if score >= 35.0:
        return SimulationRiskGrade.MODERATE
    return SimulationRiskGrade.LOW


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = _average(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _standard_deviation(values: Sequence[float]) -> float:
    return sqrt(_variance(values))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
