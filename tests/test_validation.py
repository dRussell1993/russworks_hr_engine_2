from russworks.main import sample_game
from russworks.validation import validate_step2


def test_sample_game_validates():
    validate_step2(sample_game())


def test_all_batters_present():
    g = sample_game()
    assert len(g.batters_for_team("TEX")) == 9
    assert len(g.batters_for_team("KC")) == 9
