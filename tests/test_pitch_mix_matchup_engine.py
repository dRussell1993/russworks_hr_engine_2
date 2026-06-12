from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, rank_cluster_batters
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, BatterReviewResult, Step3ReviewEngine
from russworks.scoring.pitchmix import (
    BatterPitchProfile,
    PitchMixEngine,
    PitchMixMatchupResult,
    PitchMixProfile,
    calculate_pitch_mix_matchup_score,
)
from russworks.slips import Step5SlipEngine


def test_pitch_mix_models_are_dataclasses():
    assert is_dataclass(PitchMixProfile)
    assert is_dataclass(BatterPitchProfile)
    assert is_dataclass(PitchMixMatchupResult)


def test_pitch_mix_engine_scores_primary_pitch_collision_heavily():
    pitcher = PitchMixProfile(
        pitcher_name="KC Starter",
        pitch_types=["fastball", "slider", "changeup"],
        pitch_usage_percentages={"fastball": 60.0, "slider": 25.0, "changeup": 15.0},
        primary_pitch="fastball",
        secondary_pitch="slider",
    )
    batter = BatterPitchProfile(
        batter_name="TEX Fastball Hunter",
        hr_rate_by_pitch_type={"fastball": 9.0, "slider": 4.0},
        barrel_rate_by_pitch_type={"fastball": 17.0, "slider": 10.0},
        slugging_by_pitch_type={"fastball": 0.720, "slider": 0.470},
        iso_by_pitch_type={"fastball": 0.360, "slider": 0.210},
        whiff_rate_by_pitch_type={"fastball": 19.0, "slider": 24.0},
    )

    result = calculate_pitch_mix_matchup_score(pitcher, batter)

    assert result.pitch_mix_matchup_score >= 70.0
    assert result.grade in {"Elite", "Strong"}
    assert result.primary_pitch_collision
    assert not result.severe_primary_weakness
    assert "fastball" in result.matched_pitches


def test_pitch_mix_engine_penalizes_severe_primary_pitch_weakness():
    pitcher = PitchMixProfile(
        pitcher_name="TEX Starter",
        pitch_types=["slider", "fastball"],
        pitch_usage_percentages={"slider": 65.0, "fastball": 35.0},
        primary_pitch="slider",
        secondary_pitch="fastball",
    )
    batter = BatterPitchProfile(
        batter_name="KC Slider Liability",
        hr_rate_by_pitch_type={"slider": 0.5, "fastball": 5.0},
        barrel_rate_by_pitch_type={"slider": 3.0, "fastball": 12.0},
        slugging_by_pitch_type={"slider": 0.250, "fastball": 0.510},
        iso_by_pitch_type={"slider": 0.070, "fastball": 0.250},
        whiff_rate_by_pitch_type={"slider": 39.0, "fastball": 23.0},
    )

    result = PitchMixEngine().score_matchup(pitcher, batter)

    assert result.severe_primary_weakness
    assert result.grade in {"Neutral", "Weak"}
    assert result.pitch_mix_matchup_score < 58.0
    assert result.components["primary_weakness_penalty"] < 0.0


def test_pitch_mix_engine_rewards_multiple_positive_collisions():
    pitcher = PitchMixProfile(
        pitcher_name="KC Starter",
        pitch_types=["fastball", "slider", "changeup"],
        pitch_usage_percentages={"fastball": 45.0, "slider": 35.0, "changeup": 20.0},
        primary_pitch="fastball",
        secondary_pitch="slider",
    )
    batter = BatterPitchProfile(
        batter_name="TEX Two-Pitch Bat",
        hr_rate_by_pitch_type={"fastball": 8.0, "slider": 7.0, "changeup": 2.0},
        barrel_rate_by_pitch_type={"fastball": 16.0, "slider": 14.0, "changeup": 6.0},
        slugging_by_pitch_type={"fastball": 0.690, "slider": 0.620, "changeup": 0.350},
        iso_by_pitch_type={"fastball": 0.340, "slider": 0.310, "changeup": 0.120},
        whiff_rate_by_pitch_type={"fastball": 20.0, "slider": 22.0, "changeup": 31.0},
    )

    result = PitchMixEngine().score_matchup(pitcher, batter)

    assert result.multiple_positive_collisions
    assert result.components["multiple_collision_bonus"] > 0.0
    assert result.grade in {"Elite", "Strong"}


def _batters(team: str, prefix: str):
    tags_by_slot = {
        1: ["YPI", "speed-power"],
        2: ["Non-superstar core"],
        4: ["Veteran", "Power Threat"],
        8: ["Catcher"],
    }
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=8.0 + slot,
            pitch_mix_score=6.0 + (slot % 3),
            projected_ab=4,
            projected_hits=1.0 + (slot / 10),
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
        date="2026-06-12",
        away_team=TeamIntake(team="KC", batters=_batters("KC", "KC"), starting_pitcher=away_pitcher),
        home_team=TeamIntake(team="TEX", batters=_batters("TEX", "TEX"), starting_pitcher=home_pitcher),
        environment=environment,
        umpire=umpire,
        weak_spots=[
            PitcherWeakSpot(pitcher_name="KC Starter", pitch="slider", weakness_score=5.0),
            PitcherWeakSpot(pitcher_name="KC Starter", pitch="fastball", weakness_score=4.0),
            PitcherWeakSpot(pitcher_name="TEX Starter", pitch="fastball", weakness_score=4.0),
        ],
        hr_matchups=[
            HRMatchup(
                batter_name="TEX Batter 1",
                pitcher_name="KC Starter",
                pitch="slider",
                matchup_score=8.5,
                exit_velo=107.0,
                angle=27.0,
                distance=411.0,
            ),
            HRMatchup(
                batter_name="TEX Batter 1",
                pitcher_name="KC Starter",
                pitch="fastball",
                matchup_score=7.5,
                exit_velo=106.0,
                angle=26.0,
                distance=404.0,
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


def test_step3_integrates_pitch_mix_matchup_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    context = engine._build_context(game, validate_step2_intake(game))

    review = engine.review_batter(game.home_team.batters[0], context)

    assert review.pitch_mix_matchup_score > 0.0
    assert review.pitch_mix_matchup_confidence > 0.0
    assert review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate", "Neutral", "Weak"}
    assert any(note.startswith("Pitch Mix") for note in review.notes)


def _review(name: str, *, pitch_mix_score: float = 0.0, pitch_mix_grade: str = "Weak") -> BatterReview:
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
        pitch_mix_matchup_score=pitch_mix_score,
        pitch_mix_matchup_confidence=0.9 if pitch_mix_score else 0.0,
        pitch_mix_matchup_grade=pitch_mix_grade,
    )


def test_step4_surfaces_pitch_mix_matchup_bats():
    report = rank_cluster_batters(
        "TEX",
        [
            _review("TEX Pitch Mix Bat", pitch_mix_score=78.0, pitch_mix_grade="Strong"),
            _review("TEX Neutral Bat", pitch_mix_score=44.0, pitch_mix_grade="Neutral"),
        ],
    )

    assert report.pitch_mix_matchup_score == 78.0
    assert report.pitch_mix_matchup_grade == "Strong"
    assert report.pitch_mix_matchup_bats == ["TEX Pitch Mix Bat"]
    assert "Pitch Mix matchup bats identified" in report.notes


def _cluster_report() -> ClusterRanking:
    report = TeamClusterReport(
        team="TEX",
        opponent="KC Starter",
        tag_grade="A+",
        cps_grade="A",
        total_cluster_score=94.25,
        cluster_strength_label="elite",
        cluster_captain="TEX Formula Captain",
        hidden_cluster_beneficiary="TEX Pitch Mix Bat",
        core_bats=["TEX Formula Captain", "TEX Pitch Mix Bat", "TEX Name Bat"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6"],
        non_superstar_cluster_bats=["TEX Pitch Mix Bat"],
        pitch_mix_matchup_bats=["TEX Pitch Mix Bat"],
        pitch_mix_matchup_score=84.0,
        pitch_mix_matchup_confidence=0.9,
        pitch_mix_matchup_grade="Elite",
        batter_count=9,
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[report])


def test_step5_includes_pitch_mix_metadata_and_justification():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    slip = portfolio.core_slips[0]
    assert slip.metadata["pitch_mix_matchup_grade"] == "Elite"
    assert slip.metadata["pitch_mix_matchup_score"] == "84.00"
    assert "Pitch Mix grade: Elite" in slip.justification


def test_postmortem_identifies_pitch_mix_matchup_archetype():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())
    report = PostMortemEngine().compare_to_step5_portfolio(
        portfolio,
        [
            {
                "team": "TEX",
                "batter": "TEX Pitch Mix Bat",
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
    assert "Pitch Mix Matchup" in report.winner_log[0].archetypes
