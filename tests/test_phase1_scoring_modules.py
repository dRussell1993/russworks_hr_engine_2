from dataclasses import is_dataclass

from russworks.cps import ClusterParticipationInput, ClusterParticipationScore, calculate_cps
from russworks.environment import EnvironmentScore, EnvironmentScoreInput, calculate_environment_score
from russworks.lstm import LineupSlotTrendInput, LineupSlotTrendMultiplier, calculate_lstm
from russworks.main import sample_game
from russworks.pvs import PitchVulnerabilityInput, PitchVulnerabilityScore, calculate_pvs
from russworks.tag import TeamAttackGrade, TeamAttackGradeInput, calculate_tag
from russworks.umpire import UmpireScore, UmpireScoreInput, calculate_umpire_score


def test_phase1_results_are_dataclasses():
    assert is_dataclass(EnvironmentScore)
    assert is_dataclass(UmpireScore)
    assert is_dataclass(LineupSlotTrendMultiplier)
    assert is_dataclass(PitchVulnerabilityScore)
    assert is_dataclass(TeamAttackGrade)
    assert is_dataclass(ClusterParticipationScore)


def test_environment_score_uses_weather_and_wind_components():
    game = sample_game()
    result = calculate_environment_score(EnvironmentScoreInput(game.environment))

    assert result.score > 0
    assert result.label in {"positive", "extreme"}
    assert result.components["weather_hr"] > 0
    assert result.components["wind"] > 0


def test_umpire_score_returns_hitter_context_for_walk_zone():
    game = sample_game()
    result = calculate_umpire_score(UmpireScoreInput(game.environment.umpire))

    assert result.score > 0
    assert result.components["zone"] > 0
    assert "hitter-friendly zone" in result.notes


def test_lstm_promotes_slot_seven_only_with_a_level_clusters():
    normal = calculate_lstm(LineupSlotTrendInput(lineup_slot=7, tag_grade="B", cps_grade="B"))
    boosted = calculate_lstm(LineupSlotTrendInput(lineup_slot=7, tag_grade="A", cps_grade="A-"))

    assert normal.score < 0
    assert boosted.score == 8.0
    assert boosted.multiplier > 1.0
    assert "slot 7 cluster override" in boosted.notes


def test_pvs_scores_direct_hr_matchup_and_weak_spot():
    game = sample_game()
    batter = next(b for b in game.batters if b.name == "Corey Seager")
    result = calculate_pvs(
        PitchVulnerabilityInput(
            batter=batter,
            pitcher=game.home_pitcher,
            weak_spots=game.weak_spots,
            hr_matchups=game.hr_matchups,
        )
    )

    assert result.score >= 15
    assert result.label == "elite"
    assert "4-Seam" in result.matched_pitches
    assert result.components["matchup"] > 0
    assert result.components["weak_spot"] > 0


def test_tag_scores_team_attack_context():
    game = sample_game()
    env = calculate_environment_score(EnvironmentScoreInput(game.environment))
    umpire = calculate_umpire_score(UmpireScoreInput(game.environment.umpire))
    result = calculate_tag(
        TeamAttackGradeInput(
            team="TEX",
            batters=game.batters_for_team("TEX"),
            opposing_pitcher=game.home_pitcher,
            environment_score=env.score,
            umpire_score=umpire.score,
        )
    )

    assert result.team == "TEX"
    assert result.score >= 60
    assert result.grade in {"A+", "A", "A-", "B+", "B", "B-"}
    assert result.components["top_half_power"] > 0


def test_cps_identifies_four_core_batters():
    game = sample_game()
    env = calculate_environment_score(EnvironmentScoreInput(game.environment))
    tag = calculate_tag(
        TeamAttackGradeInput(
            team="KC",
            batters=game.batters_for_team("KC"),
            opposing_pitcher=game.away_pitcher,
            environment_score=env.score,
        )
    )
    result = calculate_cps(
        ClusterParticipationInput(
            team="KC",
            batters=game.batters_for_team("KC"),
            tag_score=tag.score,
            environment_score=env.score,
        )
    )

    assert result.team == "KC"
    assert len(result.core_batters) == 4
    assert result.score >= 60
    assert result.components["concentration"] > 0
