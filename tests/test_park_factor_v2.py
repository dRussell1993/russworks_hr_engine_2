from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, rank_cluster_batters
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, Step3ReviewEngine
from russworks.scoring.parkfactor import (
    ParkFactorEngine,
    ParkFactorProfile,
    ParkFactorResult,
    calculate_park_factor_score,
)
from russworks.slips import Step5SlipEngine


def test_park_factor_models_are_dataclasses():
    assert is_dataclass(ParkFactorProfile)
    assert is_dataclass(ParkFactorResult)


def test_park_factor_rewards_pull_side_carry_and_weather_without_merging_components():
    result = calculate_park_factor_score(
        ParkFactorProfile(
            park_name="Coors Field",
            handedness="L",
            pull_side="right_field",
            weather_boost=14.0,
            roof_status="open",
            wind_speed=12.0,
            wind_direction="out to right",
            temperature=88.0,
            humidity=55.0,
            hr_park_factor=0.55,
            left_field_carry=8.0,
            center_field_carry=9.0,
            right_field_carry=13.0,
        )
    )

    assert result.park_factor_score >= 82.0
    assert result.grade == "Elite"
    assert result.raw_park_component > 0.0
    assert result.same_day_weather_component > 0.0
    assert result.path_component > 0.0
    assert "weather-assisted carry" in result.notes
    assert "pull-side carry boost" in result.notes


def test_park_factor_suppresses_closed_roof_and_inbound_wind():
    result = ParkFactorEngine().score_profile(
        ParkFactorProfile(
            park_name="Roof Park",
            handedness="R",
            pull_side="left_field",
            weather_boost=-4.0,
            roof_status="closed",
            wind_speed=14.0,
            wind_direction="in from left",
            temperature=64.0,
            humidity=38.0,
            hr_park_factor=-0.15,
            left_field_carry=-4.0,
            center_field_carry=-2.0,
            right_field_carry=-1.0,
        )
    )

    assert result.grade in {"Neutral", "Suppressive"}
    assert result.roof_component < 0.0
    assert result.same_day_weather_component < 0.0
    assert "roof suppression" in result.notes


def _batters(team: str, prefix: str):
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.L if slot == 2 else Handedness.R,
            hr_pct=9.0 + slot,
            pitch_mix_score=6.0 + (slot % 3),
            projected_ab=4,
            projected_hits=1.0,
            tags=["Non-superstar core"] if slot == 2 else [],
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _complete_game():
    away_pitcher = PitcherIntake(
        name="KC Starter",
        team="KC",
        throws=Handedness.R,
        projected_ip=4.4,
        projected_hr=1.7,
        projected_hits=6.4,
        projected_bb=2.7,
        confirmed=True,
    )
    home_pitcher = PitcherIntake(
        name="TEX Starter",
        team="TEX",
        throws=Handedness.L,
        projected_ip=6.2,
        projected_hr=1.1,
        projected_hits=5.4,
        projected_bb=1.6,
        confirmed=True,
    )
    environment = GameEnvironment(
        game_id="tex-kc-1",
        date="2026-06-13",
        away_team="KC",
        home_team="TEX",
        park="Coors Field",
        temperature_f=88.0,
        wind_mph=12.0,
        wind_direction="out to right",
        humidity_pct=55.0,
        roof="open",
        weather_hr_pct=8.0,
        weather_distance_ft=12.0,
        park_hr_factor=0.55,
    )
    umpire = Umpire(
        name="Russ Zone",
        zone_type="Hitter",
        called_strike_rate=0.47,
        accuracy=0.92,
        consistency=0.91,
        run_lean=1.2,
    )
    return GameIntake(
        game_id="tex-kc-1",
        date="2026-06-13",
        away_team=TeamIntake(team="KC", batters=_batters("KC", "KC"), starting_pitcher=away_pitcher),
        home_team=TeamIntake(team="TEX", batters=_batters("TEX", "TEX"), starting_pitcher=home_pitcher),
        environment=environment,
        umpire=umpire,
        weak_spots=[
            PitcherWeakSpot(pitcher_name="KC Starter", pitch="slider", weakness_score=5.0),
            PitcherWeakSpot(pitcher_name="TEX Starter", pitch="fastball", weakness_score=4.0),
        ],
        hr_matchups=[
            HRMatchup(
                batter_name="TEX Batter 2",
                pitcher_name="KC Starter",
                pitch="slider",
                matchup_score=8.0,
                exit_velo=106.0,
                angle=27.0,
                distance=405.0,
            ),
            HRMatchup(
                batter_name="KC Batter 4",
                pitcher_name="TEX Starter",
                pitch="fastball",
                matchup_score=7.0,
                exit_velo=104.0,
                angle=25.0,
                distance=398.0,
            ),
        ],
    )


def test_step3_integrates_park_factor_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    context = engine._build_context(game, validate_step2_intake(game))

    review = engine.review_batter(game.home_team.batters[1], context)

    assert review.park_factor_score > 0.0
    assert review.park_factor_confidence > 0.0
    assert review.park_factor_grade in {"Elite", "Strong", "Moderate", "Neutral", "Suppressive"}
    assert any(note.startswith("Park Factor") for note in review.notes)


def _review(name: str, *, park_score: float = 0.0, park_grade: str = "Neutral") -> BatterReview:
    return BatterReview(
        batter_name=name,
        team="TEX",
        opponent="KC Starter",
        lineup_slot=3,
        hr_pct=16.0,
        lstm_score=12.0,
        tag_contribution=92.0,
        cps_contribution=91.0,
        pvs_contribution=12.0,
        environment_score=10.0,
        umpire_score=2.0,
        ypi_flag=False,
        catcher_power_flag=False,
        veteran_bounce_flag=False,
        non_superstar_core_flag=True,
        weak_spot_collision_flag=True,
        final_russ_score=82.0,
        russ_tier=RussTier.GOLD,
        notes=[],
        park_factor_score=park_score,
        park_factor_confidence=0.9 if park_score else 0.0,
        park_factor_grade=park_grade,
    )


def test_step4_surfaces_park_factor_bats():
    report = rank_cluster_batters(
        "TEX",
        [
            _review("TEX Park Bat", park_score=78.0, park_grade="Strong"),
            _review("TEX Neutral Bat", park_score=44.0, park_grade="Neutral"),
        ],
    )

    assert report.park_factor_score == 78.0
    assert report.park_factor_grade == "Strong"
    assert report.park_factor_bats == ["TEX Park Bat"]
    assert "Park Factor bats identified" in report.notes


def _cluster_report() -> ClusterRanking:
    report = TeamClusterReport(
        team="TEX",
        opponent="KC Starter",
        tag_grade="A+",
        cps_grade="A",
        total_cluster_score=94.25,
        cluster_strength_label="elite",
        cluster_captain="TEX Formula Captain",
        hidden_cluster_beneficiary="TEX Park Bat",
        core_bats=["TEX Formula Captain", "TEX Park Bat", "TEX Name Bat"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6"],
        non_superstar_cluster_bats=["TEX Park Bat"],
        park_factor_bats=["TEX Park Bat"],
        park_factor_score=84.0,
        park_factor_confidence=0.9,
        park_factor_grade="Elite",
        batter_count=9,
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[report])


def test_step5_includes_park_factor_metadata_and_justification():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    slip = portfolio.core_slips[0]
    assert slip.metadata["park_factor_grade"] == "Elite"
    assert slip.metadata["park_factor_score"] == "84.00"
    assert "Park Factor grade: Elite" in slip.justification


def test_postmortem_identifies_park_factor_archetype():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())
    report = PostMortemEngine().compare_to_step5_portfolio(
        portfolio,
        [
            {
                "team": "TEX",
                "batter": "TEX Park Bat",
                "pitch": "slider",
                "pitcher": "KC Starter",
                "inning": 4,
                "exit_velocity": 106.0,
                "distance": 409.0,
                "angle": 27.0,
            }
        ],
    )

    assert report.winner_log
    assert "Park Factor" in report.winner_log[0].archetypes
