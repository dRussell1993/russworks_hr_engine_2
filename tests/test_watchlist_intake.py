from dataclasses import is_dataclass

import pytest

from russworks.intake import (
    BatterIntake,
    GameIntake,
    IntakeValidationError,
    PitcherIntake,
    ReviewQueue,
    TeamIntake,
    WatchlistImport,
    validate_step2_intake,
)
from russworks.models import GameEnvironment, HRMatchup, Handedness, PitcherWeakSpot, Umpire


def _batters(team: str):
    return [
        BatterIntake(
            name=f"{team} Batter {slot}",
            team=team,
            lineup_slot=slot,
            bats=Handedness.R,
            confirmed=True,
        )
        for slot in range(1, 10)
    ]


def _complete_game() -> GameIntake:
    umpire = Umpire("Test Umpire")
    return GameIntake(
        game_id="TEX-KC-2026-06-11",
        date="2026-06-11",
        away_team=TeamIntake("TEX", _batters("TEX"), PitcherIntake("Away Pitcher", "TEX", confirmed=True)),
        home_team=TeamIntake("KC", _batters("KC"), PitcherIntake("Home Pitcher", "KC", confirmed=True)),
        environment=GameEnvironment(
            game_id="TEX-KC-2026-06-11",
            date="2026-06-11",
            away_team="TEX",
            home_team="KC",
            park="Kauffman Stadium",
            umpire=umpire,
        ),
        umpire=umpire,
        weak_spots=[PitcherWeakSpot("Away Pitcher", "Slider", weakness_score=6)],
        hr_matchups=[HRMatchup("KC Batter 1", "Away Pitcher", "Slider", matchup_score=6)],
    )


def test_intake_models_are_dataclasses():
    assert is_dataclass(BatterIntake)
    assert is_dataclass(TeamIntake)
    assert is_dataclass(GameIntake)
    assert is_dataclass(WatchlistImport)
    assert is_dataclass(ReviewQueue)


def test_complete_intake_builds_valid_review_queue_for_every_batter():
    queue = validate_step2_intake(_complete_game())

    assert queue.is_valid
    assert queue.total_batters == 18
    assert queue.validated_batters == 18
    assert len(queue.review_required) == 18
    assert queue.missing_data == {}


def test_missing_lineup_positions_are_flagged_without_dropping_review_required():
    game = _complete_game()
    game.away_team.batters[0] = BatterIntake("Missing Slot", "TEX", confirmed=True)

    queue = validate_step2_intake(game)

    assert not queue.is_valid
    assert queue.total_batters == 18
    assert queue.validated_batters == 17
    assert queue.missing_data["lineup_position"] == ["Missing Slot"]
    assert any(batter.name == "Missing Slot" for batter in queue.review_required)


def test_missing_step2_inputs_are_grouped_by_required_category():
    game = GameIntake(
        game_id="BAD-GAME",
        date="2026-06-11",
        away_team=TeamIntake("TEX", [BatterIntake("Unconfirmed", "TEX")], None),
        home_team=TeamIntake("KC", [], None),
    )

    queue = validate_step2_intake(game)

    assert not queue.is_valid
    assert "environment" in queue.missing_data
    assert "umpire" in queue.missing_data
    assert "pitcher" in queue.missing_data
    assert "weak_spot" in queue.missing_data
    assert "hr_matchup" in queue.missing_data
    assert "lineup" in queue.missing_data
    assert "lineup_position" in queue.missing_data
    assert "confirmed_lineup" in queue.missing_data


def test_no_shortcuts_gate_can_raise_validation_error():
    game = _complete_game()
    game.home_team.batters[8] = BatterIntake("Unconfirmed Batter", "KC", lineup_slot=9, confirmed=False)

    with pytest.raises(IntakeValidationError) as exc:
        validate_step2_intake(game, raise_on_error=True)

    assert "Step 2 blocked" in str(exc.value)
    assert "confirmed_lineup" in str(exc.value)
