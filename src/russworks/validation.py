from __future__ import annotations

from .models import Game


class StepValidationError(RuntimeError):
    pass


def validate_step2(game: Game) -> None:
    missing = []
    if not game.environment:
        missing.append("environment")
    if not game.environment.umpire:
        missing.append("umpire")
    if not game.away_pitcher or not game.home_pitcher:
        missing.append("pitchers")
    if not game.batters:
        missing.append("lineups/batters")
    else:
        teams = {game.environment.away_team, game.environment.home_team}
        for t in teams:
            team_count = len([b for b in game.batters if b.team == t])
            if team_count < 9:
                missing.append(f"full lineup for {t}")
    if not game.weak_spots:
        missing.append("pitcher weak spots")
    if not game.hr_matchups:
        missing.append("HR matchup data")
    if missing:
        raise StepValidationError("Step 3 blocked. Missing Step 2 inputs: " + ", ".join(missing))
