from dataclasses import is_dataclass

from russworks.intake import BatterIntake, GameIntake, PitcherIntake, TeamIntake, validate_step2_intake
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire
from russworks.review import Step3ReviewEngine, review_batter
from russworks.scoring.weakspot import (
    CollisionResult,
    PitcherWeakSpotProfile,
    WeakSpotCollisionEngine,
    WeakSpotProfile,
    calculate_weak_spot_collision,
)


def _batters(team: str, prefix: str):
    return [
        BatterIntake(
            name=f"{prefix} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R if slot % 2 else Handedness.L,
            hr_pct=8.0 + slot,
            pitch_mix_score=6.0 + (slot % 2),
            projected_ab=4,
            projected_hits=1.0,
            tags=["YPI"] if slot == 1 else ["Catcher"] if slot == 8 else [],
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


def test_weakspot_models_are_dataclasses():
    assert is_dataclass(WeakSpotProfile)
    assert is_dataclass(PitcherWeakSpotProfile)
    assert is_dataclass(CollisionResult)


def test_weakspot_collision_scores_elite_overlap():
    batter = WeakSpotProfile(
        batter_name="Power Bat",
        hot_zones=["up-in", "middle", "down-away"],
        barrel_zones=["middle", "down-away"],
        pitch_type_performance={"fastball": 95.0, "slider": 80.0, "changeup": 75.0},
    )
    pitcher = PitcherWeakSpotProfile(
        pitcher_name="Attackable Arm",
        weak_zones=["up-in", "middle", "down-away"],
        pitch_mix={"fastball": 60.0, "slider": 25.0, "changeup": 15.0},
        attack_locations=["up-in", "middle", "down-away"],
    )

    result = calculate_weak_spot_collision(batter, pitcher)

    assert result.collision_score == 100.0
    assert result.collision_confidence == 1.0
    assert result.collision_grade == "A+"
    assert result.matched_zones == ["down-away", "middle", "up-in"]
    assert result.matched_pitches == ["changeup", "fastball", "slider"]


def test_weakspot_collision_grades_miss_as_d():
    result = WeakSpotCollisionEngine().score_collision(
        WeakSpotProfile(batter_name="Cold Bat", hot_zones=["up-in"], barrel_zones=[], pitch_type_performance={"fastball": 30.0}),
        PitcherWeakSpotProfile(pitcher_name="Clean Arm", weak_zones=["down-away"], pitch_mix={"slider": 20.0}, attack_locations=["middle"]),
    )

    assert result.collision_score < 25.0
    assert result.collision_grade == "D"
    assert result.matched_zones == []
    assert result.matched_pitches == []


def test_step3_review_includes_weakspot_collision_result():
    game = _complete_game()
    engine = Step3ReviewEngine()
    queue = validate_step2_intake(game)
    context = engine._build_context(game, queue)

    review = review_batter(game.home_team.batters[0], context)

    assert review.batter_name == "TEX Batter 1"
    assert review.weak_spot_collision_flag
    assert review.weak_spot_collision_score > 0
    assert review.weak_spot_collision_confidence > 0
    assert review.weak_spot_collision_grade in {"A+", "A", "B", "C", "D"}
