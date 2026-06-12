from dataclasses import is_dataclass

from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, RussTier, Umpire
from russworks.review import BatterReview, BatterReviewResult, Step3ReviewEngine, review_all_batters, review_batter


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
            hr_pct=7.5 + slot,
            pitch_mix_score=5.5 + (slot % 3),
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
            PitcherWeakSpot(pitcher_name="TEX Starter", pitch="fastball", weakness_score=4.0),
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


def test_step3_review_models_are_dataclasses():
    assert is_dataclass(BatterReview)
    assert is_dataclass(BatterReviewResult)


def test_review_all_batters_reviews_every_validated_batter():
    result = review_all_batters(_complete_game())

    assert result.success
    assert result.total_batters == 18
    assert result.reviewed_batters == 18
    assert len(result.reviews) == 18
    assert result.errors == []
    assert result.skipped_batters == []

    first = result.reviews[0]
    assert first.batter_name
    assert first.team in {"KC", "TEX"}
    assert first.opponent in {"KC Starter", "TEX Starter"}
    assert 1 <= first.lineup_slot <= 9
    assert first.hr_pct > 0
    assert isinstance(first.lstm_score, float)
    assert isinstance(first.tag_contribution, float)
    assert isinstance(first.cps_contribution, float)
    assert isinstance(first.pvs_contribution, float)
    assert isinstance(first.environment_score, float)
    assert isinstance(first.umpire_score, float)
    assert isinstance(first.final_russ_score, float)
    assert isinstance(first.russ_tier, RussTier)


def test_step3_blocks_when_step2_validation_is_incomplete():
    game = _complete_game()
    incomplete = GameIntake(
        game_id=game.game_id,
        date=game.date,
        away_team=game.away_team,
        home_team=game.home_team,
        environment=game.environment,
        umpire=game.umpire,
        weak_spots=[],
        hr_matchups=game.hr_matchups,
    )

    result = review_all_batters(incomplete)

    assert not result.success
    assert result.total_batters == 18
    assert result.reviewed_batters == 0
    assert result.reviews == []
    assert "Step 2 validation incomplete" in result.errors[0]
    assert len(result.skipped_batters) == 18


def test_review_batter_sets_step3_flags_and_scores():
    game = _complete_game()
    engine = Step3ReviewEngine()
    queue = validate_step2_intake(game)
    context = engine._build_context(game, queue)

    tex_ypi = review_batter(game.home_team.batters[0], context)
    tex_catcher = review_batter(game.home_team.batters[7], context)
    kc_veteran = review_batter(game.away_team.batters[3], context)

    assert tex_ypi.ypi_flag
    assert tex_ypi.weak_spot_collision_flag
    assert tex_ypi.final_russ_score >= 20.0
    assert tex_ypi.russ_tier in set(RussTier)

    assert tex_catcher.catcher_power_flag
    assert kc_veteran.veteran_bounce_flag
    assert any(review.non_superstar_core_flag for review in review_all_batters(game).reviews)
