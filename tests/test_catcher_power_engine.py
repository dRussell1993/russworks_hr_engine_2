from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, generate_cluster_report
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, BatterReviewResult, Step3ReviewEngine, review_batter
from russworks.scoring.catcher import (
    CatcherPowerEngine,
    CatcherPowerResult,
    CatcherProfile,
    calculate_catcher_power_score,
)
from russworks.slips import generate_slip_portfolio


def test_catcher_power_models_are_dataclasses():
    assert is_dataclass(CatcherProfile)
    assert is_dataclass(CatcherPowerResult)


def test_catcher_power_engine_detects_power_catcher_context():
    result = calculate_catcher_power_score(
        CatcherProfile(
            batter_name="Power Catcher",
            primary_position="C",
            games_caught=82,
            lineup_slot=4,
            recent_hr_trend=2.5,
            barrel_rate=12.0,
            hard_hit_rate=47.0,
            exit_velocity=92.0,
            fly_ball_profile=42.0,
            pull_profile=46.0,
            team_tag=91.0,
            team_cps=90.0,
        )
    )

    assert result.catcher_power_score >= 82.0
    assert result.confidence >= 0.9
    assert result.grade == "Elite"
    assert result.is_catcher
    assert result.above_average_hr_upside
    assert result.strong_cluster_context
    assert result.premium_lineup_slot


def test_catcher_power_engine_only_applies_to_catchers():
    result = CatcherPowerEngine().score_profile(
        CatcherProfile(
            batter_name="Corner Power Bat",
            primary_position="1B",
            games_caught=0,
            lineup_slot=4,
            recent_hr_trend=3.0,
            barrel_rate=14.0,
            hard_hit_rate=50.0,
            exit_velocity=94.0,
            fly_ball_profile=44.0,
            pull_profile=48.0,
            team_tag=92.0,
            team_cps=91.0,
        )
    )

    assert result.catcher_power_score == 0.0
    assert result.grade == "Weak"
    assert not result.is_catcher
    assert "non-catchers" in result.notes[0]


def test_catcher_power_engine_does_not_boost_weak_catcher_by_position_alone():
    result = CatcherPowerEngine().score_profile(
        CatcherProfile(
            batter_name="Weak Catcher",
            primary_position="C",
            games_caught=70,
            lineup_slot=8,
            recent_hr_trend=0.0,
            barrel_rate=4.0,
            hard_hit_rate=31.0,
            exit_velocity=86.0,
            fly_ball_profile=27.0,
            pull_profile=33.0,
            team_tag=88.0,
            team_cps=88.0,
        )
    )

    assert result.is_catcher
    assert not result.above_average_hr_upside
    assert result.grade in {"Neutral", "Weak"}
    assert "catcher status alone is not enough" in result.notes


def _batters(team: str, prefix: str):
    tags_by_slot = {
        1: ["YPI", "young"],
        4: ["Veteran", "Power Threat", "drought"],
        5: ["Catcher"],
    }
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=10.0 + slot,
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
                batter_name="TEX Batter 5",
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


def test_step3_review_includes_catcher_power_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    queue = validate_step2_intake(game)
    context = engine._build_context(game, queue)

    review = review_batter(game.home_team.batters[4], context)

    assert review.batter_name == "TEX Batter 5"
    assert review.catcher_power_flag
    assert review.catcher_power_score > 0.0
    assert review.catcher_power_confidence > 0.0
    assert review.catcher_power_grade in {"Elite", "Strong", "Moderate", "Neutral", "Weak"}
    assert any(note.startswith("Catcher Power ") for note in review.notes)


def _review(name: str, team: str, opponent: str, slot: int, *, catcher_score: float, catcher_grade: str, catcher: bool = True) -> BatterReview:
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
        catcher_power_flag=catcher,
        veteran_bounce_flag=False,
        non_superstar_core_flag=True,
        weak_spot_collision_flag=False,
        final_russ_score=82.0,
        russ_tier=RussTier.GOLD,
        notes=[f"Catcher Power {catcher_grade}"],
        catcher_power_score=catcher_score,
        catcher_power_confidence=0.9,
        catcher_power_grade=catcher_grade,
    )


def test_step4_cluster_report_carries_catcher_power_pressure():
    reviews = [
        _review("TEX Power Catcher", "TEX", "KC Starter", 5, catcher_score=78.0, catcher_grade="Strong"),
        _review("TEX Support Bat", "TEX", "KC Starter", 3, catcher_score=52.0, catcher_grade="Neutral", catcher=False),
    ]
    result = generate_cluster_report(BatterReviewResult(total_batters=2, reviewed_batters=2, reviews=reviews))

    assert result.success
    report = result.ranked_teams[0]
    assert report.catcher_power_score == 78.0
    assert report.catcher_power_confidence == 0.9
    assert report.catcher_power_grade == "Strong"
    assert "Strong Catcher Power cluster pressure" in report.notes
    assert report.catcher_power_bats == ["TEX Power Catcher"]


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
        core_bats=["TEX Formula Captain", "TEX Power Catcher", "TEX Name Bat"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6", "TEX Secondary 7"],
        non_superstar_cluster_bats=["TEX Hidden Value"],
        catcher_power_bats=["TEX Power Catcher"],
        ypi_bats=["TEX YPI Bat"],
        veteran_bounce_bats=["TEX Veteran Rebound"],
        batter_count=9,
        ypi_score=55.0,
        ypi_confidence=0.8,
        ypi_grade="Neutral",
        veteran_bounce_score=65.0,
        veteran_bounce_confidence=0.8,
        veteran_bounce_grade="Moderate",
        catcher_power_score=84.0,
        catcher_power_confidence=0.95,
        catcher_power_grade="Elite",
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[tex])


def test_step5_slips_include_catcher_power_metadata_and_justification():
    portfolio = generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    assert portfolio.all_slips
    assert any(slip.metadata["catcher_power_grade"] == "Elite" for slip in portfolio.all_slips)
    assert any(slip.metadata["catcher_power_score"] == "84.00" for slip in portfolio.all_slips)
    assert any("Catcher Power grade: Elite" in slip.justification for slip in portfolio.all_slips)


def test_postmortem_detects_catcher_power_archetype_from_step5_portfolio():
    report = PostMortemEngine().compare_to_step5_portfolio(
        generate_slip_portfolio(_cluster_report()),
        [
            {
                "team": "TEX",
                "batter": "TEX Power Catcher",
                "pitch": "slider",
                "pitcher": "KC Starter",
                "inning": 4,
                "exit_velocity": 106.4,
                "distance": 412.0,
                "angle": 28.0,
            }
        ],
    )

    winner = next(entry for entry in report.winner_log if entry.batter == "TEX Power Catcher")
    assert winner.source == "step5_hit"
    assert "Catcher Power" in winner.archetypes
