from dataclasses import is_dataclass
import json

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.models import RussTier
from russworks.reports import (
    FullRussWorksReport,
    REPORT_SCHEMA_VERSION,
    ReportContext,
    ReportGenerator,
    Step3Report,
    Step4Report,
    Step5Report,
    load_full_report_payload,
)
from russworks.review import BatterReview, BatterReviewResult
from russworks.slips import Slip, SlipLeg, SlipPortfolio


def _review(
    name: str,
    team: str,
    slot: int,
    *,
    russ_score: float,
    ypi: bool = False,
    veteran: bool = False,
    catcher: bool = False,
    non_superstar: bool = False,
) -> BatterReview:
    return BatterReview(
        batter_name=name,
        team=team,
        opponent="KC Starter" if team == "TEX" else "TEX Starter",
        lineup_slot=slot,
        hr_pct=14.0,
        lstm_score=9.0,
        tag_contribution=91.0,
        cps_contribution=89.0,
        pvs_contribution=12.0,
        environment_score=10.0,
        umpire_score=2.0,
        ypi_flag=ypi,
        catcher_power_flag=catcher,
        veteran_bounce_flag=veteran,
        non_superstar_core_flag=non_superstar,
        weak_spot_collision_flag=True,
        final_russ_score=russ_score,
        russ_tier=RussTier.GOLD,
        notes=["Weak-Spot Collision"],
        weak_spot_collision_score=82.0,
        weak_spot_collision_confidence=0.84,
        weak_spot_collision_grade="A",
        ypi_score=78.0 if ypi else 0.0,
        ypi_confidence=0.72 if ypi else 0.0,
        ypi_grade="Strong" if ypi else "Weak",
        veteran_bounce_score=74.0 if veteran else 0.0,
        veteran_bounce_confidence=0.68 if veteran else 0.0,
        veteran_bounce_grade="Strong" if veteran else "Weak",
        catcher_power_score=73.0 if catcher else 0.0,
        catcher_power_confidence=0.66 if catcher else 0.0,
        catcher_power_grade="Strong" if catcher else "Weak",
        pitch_mix_matchup_score=80.0,
        pitch_mix_matchup_confidence=0.75,
        pitch_mix_matchup_grade="Strong",
        bullpen_exposure_score=76.0,
        bullpen_exposure_confidence=0.71,
        bullpen_exposure_grade="Strong",
        park_factor_score=72.0,
        park_factor_confidence=0.64,
        park_factor_grade="Strong",
    )


def _step3_results() -> BatterReviewResult:
    reviews = [
        _review("TEX Captain", "TEX", 3, russ_score=86.0, non_superstar=True),
        _review("TEX YPI", "TEX", 1, russ_score=82.0, ypi=True, non_superstar=True),
        _review("TEX Catcher", "TEX", 8, russ_score=78.0, catcher=True, non_superstar=True),
        _review("KC Veteran", "KC", 4, russ_score=80.0, veteran=True),
    ]
    return BatterReviewResult(total_batters=len(reviews), reviewed_batters=len(reviews), reviews=reviews)


def _cluster_ranking() -> ClusterRanking:
    return ClusterRanking(
        total_teams=2,
        total_batters=4,
        ranked_teams=[
            TeamClusterReport(
                team="TEX",
                opponent="KC Starter",
                tag_grade="A+",
                cps_grade="A",
                total_cluster_score=94.0,
                cluster_strength_label="elite",
                cluster_captain="TEX Captain",
                hidden_cluster_beneficiary="TEX YPI",
                core_bats=["TEX Captain", "TEX YPI"],
                secondary_bats=["TEX Catcher"],
                non_superstar_cluster_bats=["TEX Captain", "TEX YPI", "TEX Catcher"],
                catcher_power_bats=["TEX Catcher"],
                ypi_bats=["TEX YPI"],
                veteran_bounce_bats=[],
                pitch_mix_matchup_bats=["TEX Captain"],
                bullpen_exposure_bats=["TEX Captain"],
                park_factor_bats=["TEX Captain"],
                batter_count=3,
                ypi_score=78.0,
                ypi_confidence=0.72,
                ypi_grade="Strong",
                catcher_power_score=73.0,
                catcher_power_confidence=0.66,
                catcher_power_grade="Strong",
            ),
            TeamClusterReport(
                team="KC",
                opponent="TEX Starter",
                tag_grade="B",
                cps_grade="B",
                total_cluster_score=76.0,
                cluster_strength_label="viable",
                cluster_captain="KC Veteran",
                hidden_cluster_beneficiary="",
                core_bats=["KC Veteran"],
                veteran_bounce_bats=["KC Veteran"],
                batter_count=1,
                veteran_bounce_score=74.0,
                veteran_bounce_confidence=0.68,
                veteran_bounce_grade="Strong",
            ),
        ],
    )


def _portfolio() -> SlipPortfolio:
    tex_leg = SlipLeg(
        batter="TEX Captain",
        team="TEX",
        tag="A+",
        cps="A",
        russ_score=94.0,
        slip_role="core",
        justification="Elite TAG/CPS cluster captain.",
    )
    ypi_leg = SlipLeg(
        batter="TEX YPI",
        team="TEX",
        tag="A+",
        cps="A",
        russ_score=94.0,
        slip_role="non-superstar core",
        justification="Hidden YPI cluster beneficiary.",
    )
    return SlipPortfolio(
        core_slips=[
            Slip(
                name="TEX Core",
                slip_type="core",
                legs=[tex_leg, ypi_leg],
                justification="Core slip from strongest TAG/CPS cluster.",
                metadata={"team": "TEX", "cluster_score": "94.00"},
            )
        ],
        non_superstar_core_slips=[
            Slip(
                name="TEX Value",
                slip_type="non_superstar_core",
                legs=[ypi_leg],
                justification="Non-superstar value slip.",
                metadata={"team": "TEX"},
            )
        ],
    )


def _context() -> ReportContext:
    return ReportContext(
        report_date="2026-06-13",
        games_reviewed=1,
        validation_status="valid",
        game_ids=["tex-kc-1"],
    )


def test_phase15_report_models_are_dataclasses():
    assert is_dataclass(ReportContext)
    assert is_dataclass(Step3Report)
    assert is_dataclass(Step4Report)
    assert is_dataclass(Step5Report)
    assert is_dataclass(FullRussWorksReport)


def test_step3_report_includes_all_phase_scoring_layers():
    report = ReportGenerator().generate_step3_report(_step3_results())

    assert report.total_batters_reviewed == 4
    row = next(item for item in report.batter_reviews if item["batter"] == "TEX Captain")

    assert row["russ_score"] == 86.0
    assert row["tier"] == "Gold"
    assert row["tag"] == 91.0
    assert row["cps"] == 89.0
    assert row["lstm"] == 9.0
    assert row["pvs"] == 12.0
    assert row["weak_spot_collision"]["grade"] == "A"
    assert row["ypi"]["grade"] == "Weak"
    assert row["veteran_bounce"]["grade"] == "Weak"
    assert row["catcher_power"]["grade"] == "Weak"
    assert row["pitch_mix"]["grade"] == "Strong"
    assert row["bullpen"]["grade"] == "Strong"
    assert row["park_factor"]["grade"] == "Strong"


def test_step4_report_generates_requested_rankings():
    report = ReportGenerator().generate_step4_report(_cluster_ranking())

    assert report.team_rankings[0]["team"] == "TEX"
    assert report.cluster_rankings[0]["core_bats"] == ["TEX Captain", "TEX YPI"]
    assert [row["batter"] for row in report.non_superstar_core_rankings[:2]] == ["TEX Captain", "TEX YPI"]
    assert report.ypi_rankings[0]["batter"] == "TEX YPI"
    assert report.veteran_bounce_rankings[0]["batter"] == "KC Veteran"
    assert report.catcher_power_rankings[0]["batter"] == "TEX Catcher"


def test_step5_report_groups_all_slip_families():
    report = ReportGenerator().generate_step5_report(_portfolio())

    assert report.core_slips[0]["name"] == "TEX Core"
    assert report.core_slips[0]["legs"][0]["batter"] == "TEX Captain"
    assert report.non_superstar_core_slips[0]["slip_type"] == "non_superstar_core"
    assert report.balanced_slips == []
    assert report.chaos_slips == []
    assert report.contrarian_slips == []


def test_full_report_exports_json_with_metadata():
    generator = ReportGenerator()
    report = generator.generate_full_report(
        context=_context(),
        step3_results=_step3_results(),
        cluster_ranking=_cluster_ranking(),
        slip_portfolio=_portfolio(),
    )

    payload = json.loads(generator.export_json(report))

    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    assert payload["context"]["report_date"] == "2026-06-13"
    assert payload["context"]["games_reviewed"] == 1
    assert payload["context"]["validation_status"] == "valid"
    assert len(payload["step3"]["batter_reviews"]) == 4
    assert payload["step4"]["team_rankings"][0]["team"] == "TEX"
    assert payload["step5"]["core_slips"][0]["metadata"]["team"] == "TEX"


def test_report_loader_accepts_versioned_and_legacy_payloads():
    generator = ReportGenerator()
    report = generator.generate_full_report(
        context=_context(),
        step3_results=_step3_results(),
        cluster_ranking=_cluster_ranking(),
        slip_portfolio=_portfolio(),
    )
    payload = json.loads(generator.export_json(report))

    versioned = load_full_report_payload(payload)
    legacy_payload = dict(payload)
    legacy_payload.pop("schema_version")
    legacy = load_full_report_payload(legacy_payload)

    assert versioned["schema_version"] == REPORT_SCHEMA_VERSION
    assert legacy["schema_version"] == "legacy"
    assert legacy["step3"]["total_batters_reviewed"] == 4


def test_report_loader_rejects_unknown_schema_versions():
    payload = {
        "schema_version": "99.0",
        "context": {},
        "step3": {},
        "step4": {},
        "step5": {},
    }

    try:
        load_full_report_payload(payload)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert "Unsupported Russ-Works report schema_version" in message
