from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.slips import (
    Slip,
    SlipLeg,
    SlipPortfolio,
    Step5SlipEngine,
    generate_balanced_slips,
    generate_chaos_slips,
    generate_contrarian_slips,
    generate_core_slips,
    generate_non_superstar_core_slips,
    generate_slip_portfolio,
)


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


def _assert_slip_metadata(slip: Slip):
    assert slip.justification
    assert slip.metadata["team"]
    assert slip.metadata["opponent"]
    assert len(slip.batters) == len(set(slip.batters))
    for leg in slip.legs:
        assert leg.batter
        assert leg.team
        assert leg.tag
        assert leg.cps
        assert leg.russ_score > 0
        assert leg.slip_role
        assert leg.justification


def test_step5_models_are_dataclasses():
    assert is_dataclass(SlipLeg)
    assert is_dataclass(Slip)
    assert is_dataclass(SlipPortfolio)


def test_step5_blocks_without_step4_results():
    portfolio = generate_slip_portfolio(None)

    assert not portfolio.success
    assert portfolio.all_slips == []
    assert "Step 5 requires Step 4 cluster results." in portfolio.errors


def test_step5_blocks_failed_step4_results():
    failed_step4 = ClusterRanking(total_teams=0, total_batters=0, errors=["Step 4 failed"])

    portfolio = generate_slip_portfolio(failed_step4)

    assert not portfolio.success
    assert "Step 5 blocked because Step 4 results contain errors." in portfolio.errors
    assert "Step 4 failed" in portfolio.errors


def test_complete_step5_portfolio_generates_all_slip_families():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    assert portfolio.core_slips
    assert portfolio.non_superstar_core_slips
    assert portfolio.balanced_slips
    assert portfolio.chaos_slips
    assert portfolio.contrarian_slips

    combinations = []
    for slip in portfolio.all_slips:
        _assert_slip_metadata(slip)
        combinations.append(tuple(sorted(slip.batters)))
    assert len(combinations) == len(set(combinations))


def test_core_slips_use_strongest_tag_cps_clusters_without_name_only_override():
    slips = generate_core_slips(_cluster_report())

    assert slips[0].metadata["team"] == "TEX"
    assert slips[0].legs[0].batter == "TEX Formula Captain"
    assert all(leg.slip_role == "core" for leg in slips[0].legs)
    assert "TAG/CPS" in slips[0].justification


def test_non_superstar_core_slips_prioritize_hidden_value_bats():
    slips = generate_non_superstar_core_slips(_cluster_report())

    assert slips[0].slip_type == "non_superstar_core"
    assert slips[0].legs[0].batter == "TEX Hidden Value"
    assert "TEX Formula Captain" not in slips[0].batters
    assert all(leg.slip_role == "non-superstar core" for leg in slips[0].legs)


def test_balanced_slips_mix_elite_cluster_and_value_bats():
    slips = generate_balanced_slips(_cluster_report())
    top_batters = slips[0].batters

    assert "TEX Formula Captain" in top_batters
    assert "TEX Hidden Value" in top_batters
    assert slips[0].slip_type == "balanced"


def test_chaos_slips_allow_catcher_power_and_ypi_profiles():
    slips = generate_chaos_slips(_cluster_report())
    top_batters = slips[0].batters

    assert "TEX Catcher Power" in top_batters
    assert "TEX YPI Bat" in top_batters
    assert slips[0].slip_type == "chaos"
    assert "Higher-variance" in slips[0].justification


def test_contrarian_slips_leverage_overlooked_clusters():
    slips = generate_contrarian_slips(_cluster_report())

    assert slips[0].metadata["team"] == "KC"
    assert "KC Hidden Value" in slips[0].batters
    assert slips[0].slip_type == "contrarian"
    assert "Lower-ownership" in slips[0].justification
