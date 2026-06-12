from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.postmortem import (
    ActualHomeRunEntry,
    AdjustmentLogEntry,
    CalibrationRecommendation,
    FalsePositiveEntry,
    LoserLogEntry,
    PostMortemEngine,
    PostMortemReport,
    WinnerLogEntry,
    compare_to_step5_portfolio,
    ingest_actual_home_runs,
)
from russworks.slips import generate_slip_portfolio


def _cluster_report() -> ClusterRanking:
    tex = TeamClusterReport(
        team="TEX",
        opponent="KC Starter",
        tag_grade="A+",
        cps_grade="A",
        total_cluster_score=94.25,
        cluster_strength_label="elite",
        cluster_captain="TEX Formula Captain",
        hidden_cluster_beneficiary="TEX Hidden Value",
        core_bats=["TEX Formula Captain", "TEX Name Bat", "TEX YPI Bat", "TEX Catcher Power"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6", "TEX Secondary 7"],
        non_superstar_cluster_bats=["TEX Hidden Value", "TEX YPI Bat", "TEX Catcher Power"],
        catcher_power_bats=["TEX Catcher Power"],
        ypi_bats=["TEX YPI Bat"],
        batter_count=9,
    )
    kc = TeamClusterReport(
        team="KC",
        opponent="TEX Starter",
        tag_grade="B",
        cps_grade="B",
        total_cluster_score=73.4,
        cluster_strength_label="viable",
        cluster_captain="KC Captain",
        hidden_cluster_beneficiary="KC Hidden Value",
        core_bats=["KC Captain", "KC Bat 1", "KC Bat 2", "KC Bat 3"],
        secondary_bats=["KC Bat 5", "KC Bat 6", "KC Bat 7", "KC Bat 8"],
        non_superstar_cluster_bats=["KC Hidden Value", "KC Bat 6"],
        catcher_power_bats=["KC Catcher Power"],
        ypi_bats=["KC YPI Bat"],
        batter_count=9,
    )
    return ClusterRanking(total_teams=2, total_batters=18, ranked_teams=[tex, kc])


def _portfolio():
    return generate_slip_portfolio(_cluster_report())


def _actual_entries():
    return [
        {
            "team": "TEX",
            "batter": "TEX YPI Bat",
            "pitch": "slider",
            "pitcher": "KC Starter",
            "inning": 2,
            "exit_velocity": 106.2,
            "distance": 411.0,
            "angle": 28.0,
        },
        {
            "team": "TEX",
            "batter": "TEX Catcher Power",
            "pitch": "fastball",
            "pitcher": "KC Starter",
            "inning": 5,
            "exit_velocity": 104.8,
            "distance": 398.0,
            "angle": 25.0,
        },
        {
            "team": "KC",
            "batter": "KC Hidden Value",
            "pitch": "changeup",
            "pitcher": "TEX Starter",
            "inning": 7,
            "exit_velocity": 101.4,
            "distance": 389.0,
            "angle": 31.0,
        },
        {
            "team": "KC",
            "batter": "KC Hidden Value",
            "pitch": "slider",
            "pitcher": "TEX Starter",
            "inning": 9,
            "exit_velocity": 102.7,
            "distance": 402.0,
            "angle": 29.0,
        },
    ]


def test_postmortem_models_are_dataclasses():
    assert is_dataclass(ActualHomeRunEntry)
    assert is_dataclass(WinnerLogEntry)
    assert is_dataclass(LoserLogEntry)
    assert is_dataclass(FalsePositiveEntry)
    assert is_dataclass(AdjustmentLogEntry)
    assert is_dataclass(PostMortemReport)
    assert is_dataclass(CalibrationRecommendation)


def test_ingest_actual_home_runs_preserves_duplicates():
    entries = ingest_actual_home_runs(_actual_entries())

    assert len(entries) == 4
    assert sum(1 for entry in entries if entry.batter == "KC Hidden Value") == 2
    assert entries[0].pitch == "slider"
    assert entries[0].inning == 2


def test_ingest_actual_home_runs_validates_required_fields():
    engine = PostMortemEngine()

    try:
        engine.ingest_actual_home_runs([{"team": "TEX", "batter": "Missing Fields"}])
        assert False, "missing fields should fail validation"
    except KeyError as exc:
        assert "pitch" in str(exc)
        assert "distance" in str(exc)


def test_compare_to_step5_portfolio_identifies_hits_and_misses():
    engine = PostMortemEngine()
    report = engine.compare_to_step5_portfolio(_portfolio(), _actual_entries())

    assert report.success
    assert len(report.actual_home_runs) == 4
    assert len(report.winner_log) == 4
    assert any(winner.batter == "TEX YPI Bat" and winner.source == "step5_hit" for winner in report.winner_log)
    assert any(winner.batter == "TEX Catcher Power" for winner in report.winner_log)
    assert sum(1 for winner in report.winner_log if winner.batter == "KC Hidden Value") == 2
    assert report.loser_log
    assert all(loser.batter not in {"TEX YPI Bat", "TEX Catcher Power", "KC Hidden Value"} for loser in report.loser_log)


def test_winner_archetypes_include_non_superstar_ypi_catcher_and_almost_made_it():
    report = PostMortemEngine().compare_to_step5_portfolio(_portfolio(), _actual_entries())
    archetypes = {archetype for winner in report.winner_log for archetype in winner.archetypes}

    assert "Non-Superstar" in archetypes
    assert "YPI" in archetypes
    assert "Catcher Power" in archetypes
    assert "Almost Made It" in archetypes


def test_false_positive_and_adjustment_logs_are_structured():
    report = PostMortemEngine().compare_to_step5_portfolio(_portfolio(), _actual_entries())

    assert report.false_positive_log
    false_positive = report.false_positive_log[0]
    assert false_positive.batter
    assert false_positive.overweighted_modules
    assert "do not auto-change" in false_positive.suggested_adjustment

    assert report.adjustment_log
    assert all(entry.module and entry.direction and entry.recommendation for entry in report.adjustment_log)


def test_calibration_recommendations_do_not_change_weights():
    report = PostMortemEngine().compare_to_step5_portfolio(_portfolio(), _actual_entries())

    assert report.calibration_recommendations
    assert all(abs(recommendation.suggested_delta) <= 0.05 for recommendation in report.calibration_recommendations)
    assert all("auto" in recommendation.rationale.lower() or "manual" in recommendation.rationale.lower() or "track" in recommendation.rationale.lower() for recommendation in report.calibration_recommendations)


def test_historical_logs_are_appended_not_overwritten():
    engine = PostMortemEngine()
    first = engine.compare_to_step5_portfolio(_portfolio(), [_actual_entries()[0]])
    second = engine.compare_to_step5_portfolio(_portfolio(), [_actual_entries()[1]])

    assert len(first.actual_home_runs) == 1
    assert len(second.actual_home_runs) == 2
    assert len(engine.generate_winner_log()) == 2


def test_module_level_compare_returns_report():
    report = compare_to_step5_portfolio(_portfolio(), _actual_entries()[:1])

    assert isinstance(report, PostMortemReport)
    assert report.success
    assert len(report.actual_home_runs) == 1
