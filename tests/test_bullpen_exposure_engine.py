from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, rank_cluster_batters
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, Step3ReviewEngine
from russworks.scoring.bullpen import (
    BullpenExposureEngine,
    BullpenExposureResult,
    BullpenProfile,
    RelieverProfile,
    calculate_bullpen_exposure_score,
)
from russworks.slips import Step5SlipEngine


def test_bullpen_models_are_dataclasses():
    assert is_dataclass(BullpenProfile)
    assert is_dataclass(RelieverProfile)
    assert is_dataclass(BullpenExposureResult)


def test_bullpen_exposure_engine_detects_weak_overworked_bullpen():
    result = calculate_bullpen_exposure_score(
        BullpenProfile(
            team="KC",
            bullpen_era=5.20,
            bullpen_hr_per_9=1.55,
            bullpen_xfip=4.80,
            strikeout_rate=19.0,
            walk_rate=10.5,
            recent_bullpen_workload=5.8,
            previous_3_day_workload=14.0,
            closer_available=False,
            relievers=[
                RelieverProfile(
                    name="KC Closer",
                    pitch_mix={"fastball": 62.0, "slider": 28.0},
                    hr_tendencies=1.45,
                    handedness="R",
                    leverage_role="closer",
                )
            ],
        )
    )

    assert result.bullpen_exposure_score >= 82.0
    assert result.grade == "Elite"
    assert result.weak_bullpen_environment
    assert result.heavy_bullpen_exposure
    assert result.overworked_bullpen
    assert result.closer_unavailable
    assert result.hr_prone_relief_corps


def test_bullpen_exposure_engine_keeps_strong_bullpen_low():
    result = BullpenExposureEngine().score_profile(
        BullpenProfile(
            team="TEX",
            bullpen_era=3.10,
            bullpen_hr_per_9=0.75,
            bullpen_xfip=3.45,
            strikeout_rate=27.0,
            walk_rate=6.5,
            recent_bullpen_workload=2.2,
            previous_3_day_workload=6.0,
            closer_available=True,
            relievers=[RelieverProfile(name="TEX Setup", hr_tendencies=0.70, handedness="L", leverage_role="setup")],
        )
    )

    assert result.grade in {"Neutral", "Weak"}
    assert not result.weak_bullpen_environment
    assert not result.heavy_bullpen_exposure
    assert not result.closer_unavailable
    assert not result.hr_prone_relief_corps


def _batters(team: str, prefix: str):
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
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
        tags=["weak bullpen", "overworked bullpen", "closer unavailable", "hr prone bullpen"],
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
        date="2026-06-13",
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


def test_step3_integrates_bullpen_exposure_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    context = engine._build_context(game, validate_step2_intake(game))

    review = engine.review_batter(game.home_team.batters[1], context)

    assert review.bullpen_exposure_score > 0.0
    assert review.bullpen_exposure_confidence > 0.0
    assert review.bullpen_exposure_grade in {"Elite", "Strong", "Moderate", "Neutral", "Weak"}
    assert any(note.startswith("Bullpen Exposure") for note in review.notes)


def _review(name: str, *, bullpen_score: float = 0.0, bullpen_grade: str = "Weak") -> BatterReview:
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
        bullpen_exposure_score=bullpen_score,
        bullpen_exposure_confidence=0.9 if bullpen_score else 0.0,
        bullpen_exposure_grade=bullpen_grade,
    )


def test_step4_surfaces_bullpen_exposure_bats():
    report = rank_cluster_batters(
        "TEX",
        [
            _review("TEX Bullpen Bat", bullpen_score=78.0, bullpen_grade="Strong"),
            _review("TEX Neutral Bat", bullpen_score=44.0, bullpen_grade="Neutral"),
        ],
    )

    assert report.bullpen_exposure_score == 78.0
    assert report.bullpen_exposure_grade == "Strong"
    assert report.bullpen_exposure_bats == ["TEX Bullpen Bat"]
    assert "Bullpen Exposure bats identified" in report.notes


def _cluster_report() -> ClusterRanking:
    report = TeamClusterReport(
        team="TEX",
        opponent="KC Starter",
        tag_grade="A+",
        cps_grade="A",
        total_cluster_score=94.25,
        cluster_strength_label="elite",
        cluster_captain="TEX Formula Captain",
        hidden_cluster_beneficiary="TEX Bullpen Bat",
        core_bats=["TEX Formula Captain", "TEX Bullpen Bat", "TEX Name Bat"],
        secondary_bats=["TEX Secondary 5", "TEX Secondary 6"],
        non_superstar_cluster_bats=["TEX Bullpen Bat"],
        bullpen_exposure_bats=["TEX Bullpen Bat"],
        bullpen_exposure_score=84.0,
        bullpen_exposure_confidence=0.9,
        bullpen_exposure_grade="Elite",
        batter_count=9,
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[report])


def test_step5_includes_bullpen_exposure_metadata_and_justification():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    slip = portfolio.core_slips[0]
    assert slip.metadata["bullpen_exposure_grade"] == "Elite"
    assert slip.metadata["bullpen_exposure_score"] == "84.00"
    assert "Bullpen Exposure grade: Elite" in slip.justification


def test_postmortem_identifies_bullpen_exposure_archetype():
    portfolio = Step5SlipEngine().generate_slip_portfolio(_cluster_report())
    report = PostMortemEngine().compare_to_step5_portfolio(
        portfolio,
        [
            {
                "team": "TEX",
                "batter": "TEX Bullpen Bat",
                "pitch": "slider",
                "pitcher": "KC Reliever",
                "inning": 7,
                "exit_velocity": 106.0,
                "distance": 409.0,
                "angle": 27.0,
            }
        ],
    )

    assert report.winner_log
    assert "Bullpen Exposure" in report.winner_log[0].archetypes
