from dataclasses import is_dataclass
import json

from russworks.backtesting import BacktestRequest, BacktestResult, BacktestSummary
from russworks.calibration import (
    CalibrationMetric,
    CalibrationRecommendation,
    CalibrationResult,
    FormulaCalibrationEngine,
    calibrate_formula,
)
from russworks.models import RussTier
from russworks.postmortem import (
    ActualHomeRunEntry,
    AdjustmentLogEntry,
    FalsePositiveEntry,
    PostMortemReport,
)
from russworks.review import BatterReview, BatterReviewResult


def _review(
    name: str,
    team: str,
    *,
    tag: float = 80.0,
    cps: float = 80.0,
    lstm: float = 8.0,
    pvs: float = 8.0,
    environment: float = 5.0,
    umpire: float = 1.0,
    weak_spot: bool = False,
    ypi: bool = False,
    veteran: bool = False,
    catcher: bool = False,
    pitch_mix: str = "Weak",
    bullpen: str = "Weak",
    park: str = "Neutral",
) -> BatterReview:
    return BatterReview(
        batter_name=name,
        team=team,
        opponent="Opponent Starter",
        lineup_slot=3,
        hr_pct=12.0,
        lstm_score=lstm,
        tag_contribution=tag,
        cps_contribution=cps,
        pvs_contribution=pvs,
        environment_score=environment,
        umpire_score=umpire,
        ypi_flag=ypi,
        catcher_power_flag=catcher,
        veteran_bounce_flag=veteran,
        non_superstar_core_flag=False,
        weak_spot_collision_flag=weak_spot,
        final_russ_score=78.0,
        russ_tier=RussTier.SILVER,
        weak_spot_collision_score=70.0 if weak_spot else 0.0,
        weak_spot_collision_confidence=0.75 if weak_spot else 0.0,
        weak_spot_collision_grade="A" if weak_spot else "D",
        ypi_score=75.0 if ypi else 0.0,
        ypi_confidence=0.70 if ypi else 0.0,
        ypi_grade="Strong" if ypi else "Weak",
        veteran_bounce_score=74.0 if veteran else 0.0,
        veteran_bounce_confidence=0.68 if veteran else 0.0,
        veteran_bounce_grade="Strong" if veteran else "Weak",
        catcher_power_score=73.0 if catcher else 0.0,
        catcher_power_confidence=0.66 if catcher else 0.0,
        catcher_power_grade="Strong" if catcher else "Weak",
        pitch_mix_matchup_score=76.0 if pitch_mix != "Weak" else 0.0,
        pitch_mix_matchup_confidence=0.70 if pitch_mix != "Weak" else 0.0,
        pitch_mix_matchup_grade=pitch_mix,
        bullpen_exposure_score=76.0 if bullpen != "Weak" else 0.0,
        bullpen_exposure_confidence=0.70 if bullpen != "Weak" else 0.0,
        bullpen_exposure_grade=bullpen,
        park_factor_score=72.0 if park != "Neutral" else 0.0,
        park_factor_confidence=0.65 if park != "Neutral" else 0.0,
        park_factor_grade=park,
    )


def _step3_results() -> BatterReviewResult:
    reviews = [
        _review("YPI Winner", "TEX", weak_spot=True, ypi=True, pitch_mix="Strong", bullpen="Strong", park="Strong"),
        _review("Veteran Winner", "KC", veteran=True, pitch_mix="Strong", bullpen="Strong", park="Strong"),
        _review("Catcher Miss", "TEX", catcher=True, pitch_mix="Moderate", bullpen="Moderate", park="Moderate"),
        _review("Weak Context HR", "OAK", tag=55.0, cps=55.0, lstm=-4.0, pvs=0.0, environment=-1.0, umpire=0.0),
        _review("TAG False Positive", "SEA", tag=92.0, cps=90.0, pvs=9.0),
    ]
    return BatterReviewResult(total_batters=len(reviews), reviewed_batters=len(reviews), reviews=reviews)


def _actual_home_runs():
    return [
        ActualHomeRunEntry("TEX", "YPI Winner", "slider", "Opponent Starter", 2, 106.0, 408.0, 27.0),
        ActualHomeRunEntry("KC", "Veteran Winner", "fastball", "Opponent Starter", 5, 104.0, 401.0, 25.0),
        ActualHomeRunEntry("OAK", "Weak Context HR", "changeup", "Opponent Starter", 7, 101.0, 390.0, 24.0),
    ]


def test_phase18_calibration_models_are_dataclasses():
    assert is_dataclass(CalibrationMetric)
    assert is_dataclass(CalibrationRecommendation)
    assert is_dataclass(CalibrationResult)


def test_calibration_measures_all_required_modules():
    result = calibrate_formula(_step3_results(), _actual_home_runs())
    metrics = {metric.module: metric for metric in result.metrics}

    expected_modules = {
        "TAG",
        "CPS",
        "LSTM",
        "PVS",
        "Environment",
        "Umpire",
        "Weak Spot Collision",
        "YPI",
        "Veteran Bounce",
        "Catcher Power",
        "Pitch Mix",
        "Bullpen Exposure",
        "Park Factor",
    }
    assert set(metrics) == expected_modules
    assert metrics["TAG"].appearances == 4
    assert metrics["TAG"].hits == 2
    assert metrics["TAG"].false_positives == 2
    assert metrics["TAG"].false_negatives == 1
    assert metrics["YPI"].hits == 1
    assert metrics["Veteran Bounce"].hits == 1
    assert metrics["Catcher Power"].false_positives == 1
    assert metrics["Weak Spot Collision"].hit_rate == 1.0


def test_calibration_generates_rankings_recommendations_and_trends():
    postmortem = PostMortemReport(
        false_positive_log=[
            FalsePositiveEntry(
                team="TEX",
                batter="Catcher Miss",
                slip_name="TEX Slip",
                slip_type="chaos",
                reason="High-confidence miss.",
                overweighted_modules=["Catcher Power"],
            )
        ],
        adjustment_log=[
            AdjustmentLogEntry(
                module="Catcher Power",
                direction="review_or_slightly_reduce",
                reason="Loser pressure.",
                evidence_count=2,
                recommendation="Review thresholds.",
            )
        ],
    )

    result = FormulaCalibrationEngine().calibrate_reviews(
        _step3_results(),
        _actual_home_runs(),
        postmortem_reports=[postmortem],
    )

    assert result.success
    assert result.strength_rankings[0].module in {"Weak Spot Collision", "YPI", "Veteran Bounce"}
    assert result.weakness_rankings
    catcher = next(item for item in result.recommended_adjustments if item.module == "Catcher Power")
    assert catcher.action in {"review_or_slightly_reduce", "review_postmortem_pressure"}
    assert any("Strongest module" in trend for trend in result.trend_summaries)
    assert any("Post-mortem pressure" in trend for trend in result.trend_summaries)


def test_calibration_json_export_contains_metrics_and_adjustments():
    engine = FormulaCalibrationEngine()
    result = engine.calibrate_reviews(_step3_results(), _actual_home_runs())
    payload = json.loads(engine.export_json(result))

    assert payload["metrics"][0]["module"]
    assert payload["strength_rankings"]
    assert payload["weakness_rankings"]
    assert payload["recommended_adjustments"]
    assert payload["trend_summaries"]


def test_calibration_can_use_backtest_summary_for_range_trends():
    backtest = BacktestResult(
        request=BacktestRequest("2026-06-13", "2026-06-14"),
        summary=BacktestSummary(
            start_date="2026-06-13",
            end_date="2026-06-14",
            dates_tested=2,
            total_games=2,
            total_batters_reviewed=36,
            total_hrs_hit=4,
            step3_hits=4,
            step4_hits=4,
            step5_hits=2,
            non_superstar_hits=2,
            ypi_hits=2,
            veteran_hits=1,
            catcher_hits=1,
            weak_spot_hits=3,
            pitch_mix_hits=3,
            step3_hit_rate=1.0,
            step4_hit_rate=1.0,
            step5_hit_rate=0.5,
            non_superstar_hit_rate=0.5,
            ypi_hit_rate=0.5,
            veteran_hit_rate=0.25,
            catcher_hit_rate=0.25,
            weak_spot_hit_rate=0.75,
            pitch_mix_hit_rate=0.75,
        ),
    )

    result = FormulaCalibrationEngine().calibrate_backtest(backtest)
    modules = {metric.module for metric in result.metrics}

    assert {"YPI", "Veteran Bounce", "Catcher Power", "Weak Spot Collision", "Pitch Mix"} <= modules
    assert any("Step 3 hit rate" in trend for trend in result.trend_summaries)
    assert result.recommended_adjustments
