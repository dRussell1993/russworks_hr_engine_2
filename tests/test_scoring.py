from russworks.main import sample_game
from russworks.scoring import score_game


def test_scores_all_batters():
    g = sample_game()
    scores = score_game(g)
    assert len(scores) == len(g.batters)
    assert all(s.final_score > 0 for s in scores)
