from dataclasses import is_dataclass

from russworks.cluster import ClusterRanking, TeamClusterReport, generate_cluster_report
from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.postmortem import PostMortemEngine
from russworks.review import BatterReview, BatterReviewResult, Step3ReviewEngine, review_batter
from russworks.scoring.ypi import YPIEngine, YPIProfile, YPIResult, calculate_ypi_score
from russworks.slips import generate_slip_portfolio


def test_ypi_models_are_dataclasses():
    assert is_dataclass(YPIProfile)
    assert is_dataclass(YPIResult)


def test_ypi_engine_detects_breakout_promotion_and_power_trends():
    result = calculate_ypi_score(
        YPIProfile(
            batter_name="Young Breakout Bat",
            age=23,
            mlb_experience=0.4,
            lineup_movement=2.5,
            recent_exit_velocity_trend=4.0,
            recent_barrel_trend=3.5,
            recent_hard_hit_trend=3.0,
            hr_trend=2.5,
            opportunity_growth=2.0,
            playing_time_growth=2.0,
            lineup_slot_promotion=2.0,
            is_superstar=False,
        )
    )

    assert result.ypi_score >= 82.0
    assert result.ypi_confidence >= 0.9
    assert result.ypi_grade == "Elite"
    assert result.breakout_candidate
    assert result.lineup_promotion_opportunity
    assert result.emerging_power_trend
    assert result.undervalued_young_hitter
    assert "breakout candidate" in result.notes


def test_ypi_engine_does_not_require_superstar_status():
    base = dict(
        batter_name="Young Value Bat",
        age=24,
        mlb_experience=1.0,
        lineup_movement=1.5,
        recent_exit_velocity_trend=2.5,
        recent_barrel_trend=2.0,
        recent_hard_hit_trend=2.0,
        hr_trend=1.5,
        opportunity_growth=1.5,
        playing_time_growth=1.5,
        lineup_slot_promotion=1.0,
    )

    value_result = YPIEngine().score_profile(YPIProfile(**base, is_superstar=False))
    superstar_result = YPIEngine().score_profile(YPIProfile(**base, is_superstar=True))

    assert value_result.ypi_score > superstar_result.ypi_score
    assert value_result.undervalued_young_hitter
    assert value_result.ypi_grade in {"Elite", "Strong", "Emerging"}


def _batters(team: str, prefix: str):
    tags_by_slot = {
        1: ["YPI", "young", "speed-power"],
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
            hr_pct=9.0 + slot,
            pitch_mix_score=6.0 + (slot % 3),
            projected_ab=4,
            projected_hits=1.1 + (slot / 10),
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
                batter_name="TEX Batter 1",
                pitcher_name="KC Starter",
                pitch="slider",
                matchup_score=8.0,
                exit_velo=106.0,
                angle=27.0,
                distance=405.0,
                notes="up-in",
            ),
            HRMatchup(
                batter_name="KC Batter 4",
                pitcher_name="TEX Starter",
                pitch="fastball",
                matchup_score=7.0,
                exit_velo=104.0,
                angle=25.0,
                distance=398.0,
                notes="middle",
            ),
        ],
    )


def test_step3_review_includes_ypi_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    queue = validate_step2_intake(game)
    context = engine._build_context(game, queue)

    review = review_batter(game.home_team.batters[0], context)

    assert review.batter_name == "TEX Batter 1"
    assert review.ypi_flag
    assert review.ypi_score > 0.0
    assert review.ypi_confidence > 0.0
    assert review.ypi_grade in {"Elite", "Strong", "Emerging", "Neutral", "Weak"}
    assert any(note.startswith("YPI ") for note in review.notes)


def _review(name: str, team: str, opponent: str, slot: int, *, ypi_score: float, ypi_grade: str, ypi: bool = True) -> BatterReview:
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
        ypi_flag=ypi,
        catcher_power_flag=False,
        veteran_bounce_flag=False,
        non_superstar_core_flag=True,
        weak_spot_collision_flag=False,
        final_russ_score=82.0,
        russ_tier=RussTier.GOLD,
        notes=[f"YPI {ypi_grade}"],
        ypi_score=ypi_score,
        ypi_confidence=0.9,
        ypi_grade=ypi_grade,
    )


def test_step4_cluster_report_carries_ypi_pressure():
    reviews = [
        _review("TEX Emerging Bat", "TEX", "KC Starter", 1, ypi_score=78.0, ypi_grade="Strong"),
        _review("TEX Support Bat", "TEX", "KC Starter", 3, ypi_score=52.0, ypi_grade="Neutral", ypi=False),
    ]
    result = generate_cluster_report(BatterReviewResult(total_batters=2, reviewed_batters=2, reviews=reviews))

    assert result.success
    report = result.ranked_teams[0]
    assert report.ypi_score == 78.0
    assert report.ypi_confidence == 0.9
    assert report.ypi_grade == "Strong"
    assert "Strong YPI cluster pressure" in report.notes
    assert report.ypi_bats == ["TEX Emerging Bat"]


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
        ypi_score=84.0,
        ypi_confidence=0.95,
        ypi_grade="Elite",
    )
    return ClusterRanking(total_teams=1, total_batters=9, ranked_teams=[tex])


def test_step5_slips_include_ypi_metadata_and_justification():
    portfolio = generate_slip_portfolio(_cluster_report())

    assert portfolio.success
    assert portfolio.all_slips
    assert any(slip.metadata["ypi_grade"] == "Elite" for slip in portfolio.all_slips)
    assert any(slip.metadata["ypi_score"] == "84.00" for slip in portfolio.all_slips)
    assert any("YPI grade: Elite" in slip.justification for slip in portfolio.all_slips)


def test_postmortem_detects_ypi_archetype_from_step5_portfolio():
    report = PostMortemEngine().compare_to_step5_portfolio(
        generate_slip_portfolio(_cluster_report()),
        [
            {
                "team": "TEX",
                "batter": "TEX YPI Bat",
                "pitch": "slider",
                "pitcher": "KC Starter",
                "inning": 4,
                "exit_velocity": 106.4,
                "distance": 412.0,
                "angle": 28.0,
            }
        ],
    )

    winner = next(entry for entry in report.winner_log if entry.batter == "TEX YPI Bat")
    assert winner.source == "step5_hit"
    assert "YPI" in winner.archetypes
