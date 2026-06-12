from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, Step4ClusterEngine, TeamClusterReport, generate_cluster_report, rank_cluster_batters
from russworks.models import RussTier
from russworks.review import BatterReview, BatterReviewResult


def _review(
    name: str,
    team: str,
    opponent: str,
    slot: int,
    *,
    tag: float,
    cps: float,
    russ: float,
    pvs: float = 8.0,
    lstm: float = 8.0,
    hr_pct: float = 12.0,
    ypi: bool = False,
    catcher: bool = False,
    non_superstar: bool = False,
    weak_collision: bool = False,
) -> BatterReview:
    return BatterReview(
        batter_name=name,
        team=team,
        opponent=opponent,
        lineup_slot=slot,
        hr_pct=hr_pct,
        lstm_score=lstm,
        tag_contribution=tag,
        cps_contribution=cps,
        pvs_contribution=pvs,
        environment_score=10.0,
        umpire_score=2.0,
        ypi_flag=ypi,
        catcher_power_flag=catcher,
        veteran_bounce_flag=False,
        non_superstar_core_flag=non_superstar,
        weak_spot_collision_flag=weak_collision,
        final_russ_score=russ,
        russ_tier=RussTier.GOLD if russ >= 80 else RussTier.SILVER,
        notes=[],
    )


def _step3_results() -> BatterReviewResult:
    reviews = [
        _review("TEX Formula Captain", "TEX", "KC Starter", 3, tag=92.0, cps=91.0, russ=86.0, pvs=16.0, lstm=13.0, hr_pct=19.0, non_superstar=True, weak_collision=True),
        _review("TEX YPI Bat", "TEX", "KC Starter", 1, tag=92.0, cps=91.0, russ=82.0, pvs=12.0, lstm=10.0, hr_pct=16.0, ypi=True, non_superstar=True),
        _review("TEX Catcher Power", "TEX", "KC Starter", 8, tag=92.0, cps=91.0, russ=78.0, pvs=10.0, lstm=-1.0, hr_pct=13.0, catcher=True, non_superstar=True),
        _review("TEX Name Bat", "TEX", "KC Starter", 4, tag=92.0, cps=91.0, russ=76.0, pvs=6.0, lstm=15.0, hr_pct=14.0),
        _review("TEX Secondary 5", "TEX", "KC Starter", 5, tag=92.0, cps=91.0, russ=72.0, pvs=6.0, lstm=7.0),
        _review("TEX Secondary 6", "TEX", "KC Starter", 6, tag=92.0, cps=91.0, russ=68.0, pvs=5.0, lstm=0.0),
        _review("TEX Secondary 7", "TEX", "KC Starter", 7, tag=92.0, cps=91.0, russ=66.0, pvs=5.0, lstm=8.0),
        _review("TEX Secondary 8", "TEX", "KC Starter", 8, tag=92.0, cps=91.0, russ=64.0, pvs=4.0, lstm=-3.0),
        _review("TEX Secondary 9", "TEX", "KC Starter", 9, tag=92.0, cps=91.0, russ=62.0, pvs=4.0, lstm=-4.0),
        _review("KC Captain", "KC", "TEX Starter", 4, tag=70.0, cps=68.0, russ=76.0, pvs=9.0, lstm=15.0),
        _review("KC Bat 1", "KC", "TEX Starter", 1, tag=70.0, cps=68.0, russ=70.0, pvs=6.0, lstm=10.0),
        _review("KC Bat 2", "KC", "TEX Starter", 2, tag=70.0, cps=68.0, russ=69.0, pvs=6.0, lstm=5.0),
        _review("KC Bat 3", "KC", "TEX Starter", 3, tag=70.0, cps=68.0, russ=68.0, pvs=5.0, lstm=12.0),
        _review("KC Bat 5", "KC", "TEX Starter", 5, tag=70.0, cps=68.0, russ=65.0, pvs=4.0, lstm=7.0),
        _review("KC Bat 6", "KC", "TEX Starter", 6, tag=70.0, cps=68.0, russ=61.0, pvs=3.0, lstm=0.0),
        _review("KC Bat 7", "KC", "TEX Starter", 7, tag=70.0, cps=68.0, russ=60.0, pvs=3.0, lstm=-2.0),
        _review("KC Bat 8", "KC", "TEX Starter", 8, tag=70.0, cps=68.0, russ=58.0, pvs=2.0, lstm=-6.0),
        _review("KC Bat 9", "KC", "TEX Starter", 9, tag=70.0, cps=68.0, russ=56.0, pvs=2.0, lstm=-8.0),
    ]
    return BatterReviewResult(total_batters=len(reviews), reviewed_batters=len(reviews), reviews=reviews)


def test_step4_models_are_dataclasses():
    assert is_dataclass(ClusterRanking)
    assert is_dataclass(TeamClusterReport)


def test_complete_step4_run_groups_every_step3_batter():
    result = generate_cluster_report(_step3_results())

    assert result.success
    assert result.total_teams == 2
    assert result.total_batters == 18
    assert result.errors == []
    assert sum(report.batter_count for report in result.ranked_teams) == 18

    top = result.ranked_teams[0]
    assert top.team == "TEX"
    assert top.opponent == "KC Starter"
    assert top.tag_grade in {"A", "A+"}
    assert top.cps_grade in {"A", "A+"}
    assert top.total_cluster_score > result.ranked_teams[1].total_cluster_score
    assert top.cluster_captain == "TEX Formula Captain"
    assert "TEX Formula Captain" in top.core_bats
    assert top.secondary_bats


def test_step4_blocks_when_step3_data_is_missing():
    result = generate_cluster_report(BatterReviewResult(total_batters=0, reviewed_batters=0, reviews=[]))

    assert not result.success
    assert result.ranked_teams == []
    assert "Step 4 requires Step 3 batter reviews" in result.errors[0]


def test_elite_tag_cps_cluster_boost_elevates_cluster():
    elite_reviews = [_review("Elite Bat", "TEX", "KC Starter", 3, tag=92.0, cps=91.0, russ=80.0)]
    non_elite_reviews = [_review("Good Bat", "TEX", "KC Starter", 3, tag=82.0, cps=81.0, russ=80.0)]

    elite = rank_cluster_batters("TEX", elite_reviews)
    non_elite = rank_cluster_batters("TEX", non_elite_reviews)

    assert elite.total_cluster_score > non_elite.total_cluster_score
    assert "elite TAG/CPS cluster boost" in elite.notes


def test_non_superstar_core_bats_are_identified():
    report = Step4ClusterEngine().rank_team_clusters(_step3_results()).ranked_teams[0]

    assert "TEX Formula Captain" in report.non_superstar_cluster_bats
    assert report.hidden_cluster_beneficiary in {"TEX YPI Bat", "TEX Catcher Power"}


def test_catcher_power_bats_are_identified():
    report = Step4ClusterEngine().rank_team_clusters(_step3_results()).ranked_teams[0]

    assert report.catcher_power_bats == ["TEX Catcher Power"]
    assert "catcher power bats identified" in report.notes


def test_ypi_bats_are_identified():
    report = Step4ClusterEngine().rank_team_clusters(_step3_results()).ranked_teams[0]

    assert report.ypi_bats == ["TEX YPI Bat"]
    assert "YPI bats identified" in report.notes
