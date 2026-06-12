from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, generate_cluster_report
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, BatterReviewResult, Step3ReviewEngine, review_batter
from russworks.scoring.veteran import (
    VeteranBounceEngine,
    VeteranBounceResult,
    VeteranProfile,
    calculate_veteran_bounce_score,
)
from russworks.slips import generate_slip_portfolio


def test_veteran_bounce_models_are_dataclasses():
    assert is_dataclass(VeteranProfile)
    assert is_dataclass(VeteranBounceResult)


def test_veteran_bounce_engine_detects_healthy_drought_rebound():
    result = calculate_veteran_bounce_score(
        VeteranProfile(
            batter_name="Veteran Rebound Bat",
            age=34,
            mlb_service_time=9.0,
            historical_hr_production=20.0,
            historical_barrel_rate=11.0,
            historical_hard_hit_rate=47.0,
            current_barrel_rate=10.8,
            current_hard_hit_rate=46.5,
            recent_hr_drought=12.0,
            lineup_slot=4,
            team_cluster_quality=91.0,
            recent_exit_velocity_trend=2.5,
            is_superstar=False,
        )
    )

    assert result.veteran_bounce_score >= 82.0
    assert result.confidence >= 0.9
    assert result.grade == "Elite"
    assert result.healthy_underlying_metrics
    assert result.temporary_hr_drought
    assert result.bounce_back_candidate
    assert "does not require superstar status" in result.notes


def test_veteran_bounce_engine_penalizes_unsupported_name_value():
    healthy_value = VeteranBounceEngine().score_profile(
        VeteranProfile(
            batter_name="Healthy Veteran",
            age=34,
            mlb_service_time=8.0,
            historical_hr_production=18.0,
            historical_barrel_rate=10.0,
            historical_hard_hit_rate=45.0,
            current_barrel_rate=10.0,
            current_hard_hit_rate=45.0,
            recent_hr_drought=10.0,
            lineup_slot=4,
            team_cluster_quality=88.0,
            recent_exit_velocity_trend=2.0,
            is_superstar=False,
        )
    )
    unsupported_name = VeteranBounceEngine().score_profile(
        VeteranProfile(
            batter_name="Unsupported Star",
            age=34,
            mlb_service_time=8.0,
            historical_hr_production=18.0,
            historical_barrel_rate=10.0,
            historical_hard_hit_rate=45.0,
            current_barrel_rate=5.0,
            current_hard_hit_rate=34.0,
            recent_hr_drought=10.0,
            lineup_slot=4,
            team_cluster_quality=88.0,
            recent_exit_velocity_trend=-1.0,
            is_superstar=True,
        )
    )

    assert healthy_value.veteran_bounce_score > unsupported_name.veteran_bounce_score
    assert healthy_value.bounce_back_candidate
    assert not unsupported_name.healthy_underlying_metrics
    assert unsupported_name.grade in {"Neutral", "Weak"}


def _batters(team: str, prefix: str):
    tags_by_slot = {
        1: ["YPI", "young"],
        4: ["Veteran", "Power Threat", "drought"],
        8: ["Catcher"],
    }
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=9.0 + slot,
            pitch_mix_score=7.0 + (slot % 2),
            projected_ab=4,
            projected_hits=1.0,
            tags=tags_by_slot.get(slot, []),
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _complete_game():
    away_pitcher = PitcherIntake(
        name="KC Starter",
        team="KC",
        throws=Handedness.R,
        projected_hr=1.6,
        projected_hits=6.2,
        confirmed=True,
    )
    home_pitcher = PitcherIntake(
        name="TEX Starter",
        team="TEX",
        throws=Handedness.L,
        projected_hr=1.4,
        projected_hits=5.8,
        confirmed=True,
    )
    environment = GameEnvironment(
        game_id="tex-kc-1",
        date="2026-06-12",
        away_team="KC",
        home_team="TEX",
        park="Globe Life Field",
        temperature_f=88.0,
        wind_mph=9.0,
        wind_direction="out",
        humidity_pct=55.0,
        weather_hr_pct=8.0,
        weather_distance_ft=12.0,
        park_hr_factor=7.0,
    )
    return GameIntake(
        game_id="tex-kc-1",
        date="2026-06-12",
        away_team=TeamIntake(team="KC", batters=_batters("KC", "KC"), starting_pitcher=away_pitcher),
        home_team=TeamIntake(team="TEX", batters=_batters("TEX", "TEX"), starting_pitcher=home_pitcher),
        environment=environment,
        umpire=Umpire(name="Russ Zone", zone_type="Hitter", called_strike_rate=0.47, accuracy=0.92, consistency=0.91, run_lean=1.2),
        weak_spots=[
            PitcherWeakSpot(pitcher_name="KC Starter", pitch="slider", zone="up-in", weakness_score=5.0, notes="up-in"),
            PitcherWeakSpot(pitcher_name="TEX Starter", pitch="fastball", zone="middle", weakness_score=4.0, notes="middle"),
        ],
        hr_matchups=[
            HRMatchup(
                batter_name="TEX Batter 4",
                pitcher_name="KC Starter",
                pitch="slider",
                matchup_score=8.0,
                exit_velo=106.0,
                angle=27.0,
                distance=405.0,
                notes="up-in",
            ),
        ],
    )


def test_step3_review_includes_veteran_bounce_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    queue = validate_step2_intake(game)
    context = engine._build_context(game, queue)

    review = review_batter(game.home_team.batters[3], context)

    assert review.batter_name == "TEX Batter 4"
    assert review.veteran_bounce_flag
    assert review.veteran_bounce_score > 0.0
    assert review.veteran_bounce_confidence > 0.0
    assert review.veteran_bounce_grade in {"Elite", "Strong", "Moderate", "Neutral", "Weak"}
    assert any(note.startswith("Veteran Bounce ") for note in review.notes)


def _review(name: str, team: str, opponent: str, slot: int, *, vet_score: float, vet_grade: str, vet: bool = True) -> BatterReview:
    return BatterReview(
        batter_name=name,
        team=team,
        opponent=opponent,
        lineup_slot=slot,
        hr_pct=16.0,
        lstm_score=10.0,
        tag_contribution=92.0,
        cps_contribution=91.0,
        pvs_contribution=12.0,
        environment_score=10.0,
        umpire_score=2.0,
        ypi_flag=False,
        catcher_power_flag=False,
        veteran_bounce_flag=vet,
        non_superstar_core_flag=True,
        weak_spot_collision_flag=False,
        final_russ_score=82.0,
        russ_tier=RussTier.GOLD,
        notes=[f"Veteran Bounce {vet_grade}"],
        veteran_bounce_score=vet_score,
        veteran_bounce_confidence=0.9,
        veteran_bounce_grade=vet_grade,
    )


def test_step4_cluster_report_carries_veteran_bounce_pressure():
    reviews = [
        _review("TEX Veteran Rebound", "TEX", "KC Starter", 4, vet_score=78.0, vet_grade="Strong"),
        _review("TEX Support Bat", "TEX", "KC Starter", 3, vet_score=52.0, vet_grade="Neutral", vet=False),
    ]
    result = generate_cluster_report(BatterReviewResult(total_batters=2, reviewed_batters=2, reviews=reviews))

    assert result.success
    report = result.ranked_teams[0]
    assert report.veteran_bounce_score == 78.0
    assert report.veteran_bounce_confidence == 0.9
    assert report.veteran_bounce_grade == "Strong"
    assert "Strong Veteran Bounce cluster pressure" in report.notes
    assert report.veteran_bounce_bats == ["TEX Veteran Rebound"]


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
        core_bats=["TEX Formula Captain", "TEX Veteran Rebound", "TEX Name Bat"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6", "TEX Secondary 7"],
        non_superstar_cluster_bats=["TEX Hidden Value"],
        catcher_power_bats=["TEX Catcher Power"],
        ypi_bats=["TEX YPI Bat"],
        veteran_bounce_bats=["TEX Veteran Rebound"],
        batter_count=9,
        ypi_score=55.0,
        ypi_confidence=0.8,
        ypi_grade="Neutral",
        veteran_bounce_score=84.0,
        veteran_bounce_confidence=0.95,
        veteran_bounce_grade="Elite",
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[tex])


def test_step5_slips_include_veteran_bounce_metadata_and_justification():
    portfolio = generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    assert portfolio.all_slips
    assert any(slip.metadata["veteran_bounce_grade"] == "Elite" for slip in portfolio.all_slips)
    assert any(slip.metadata["veteran_bounce_score"] == "84.00" for slip in portfolio.all_slips)
    assert any("Veteran Bounce grade: Elite" in slip.justification for slip in portfolio.all_slips)


def test_postmortem_detects_veteran_bounce_archetype_from_step5_portfolio():
    report = PostMortemEngine().compare_to_step5_portfolio(
        generate_slip_portfolio(_cluster_report()),
        [
            {
                "team": "TEX",
                "batter": "TEX Veteran Rebound",
                "pitch": "slider",
                "pitcher": "KC Starter",
                "inning": 4,
                "exit_velocity": 106.4,
                "distance": 412.0,
                "angle": 28.0,
            }
        ],
    )

    winner = next(entry for entry in report.winner_log if entry.batter == "TEX Veteran Rebound")
    assert winner.source == "step5_hit"
    assert "Veteran Bounce" in winner.archetypes
