from __future__ import annotations

import argparse
from pathlib import Path

from .models import Batter, Game, GameEnvironment, Handedness, HRMatchup, Pitcher, PitcherWeakSpot, Umpire
from .reports import step2_report, step3_report, step4_report, step5_report
from .scoring import score_game
from .slips import build_slips


def sample_game() -> Game:
    env = GameEnvironment(
        game_id="SAMPLE-TEX-KC",
        date="2026-06-11",
        away_team="TEX",
        home_team="KC",
        park="Kauffman Stadium",
        temperature_f=86,
        wind_mph=18,
        wind_direction="out to CF",
        humidity_pct=63,
        roof="open",
        weather_hr_pct=42,
        weather_distance_ft=24.7,
        umpire=Umpire("Chris Segal", "Stingy Walks", 32.6, 92.5, 40, 0),
    )
    away_p = Pitcher("Kumar Rocker", "TEX", Handedness.R, ["Reliable SP", "Hitter's Park"], projected_hr=1.06, projected_hits=5.51, projected_bb=2.13)
    home_p = Pitcher("Michael Wacha", "KC", Handedness.R, ["Reliable SP", "Hitter's Park"], projected_hr=0.79, projected_hits=5.43, projected_bb=1.69)
    batters = [
        Batter("Wyatt Langford", "TEX", Handedness.R, 1, 22, 3.3, tags=["YPI", "Everyday Bat"]),
        Batter("Corey Seager", "TEX", Handedness.L, 2, 26, 4.3, tags=["Superstar", "Power Threat"]),
        Batter("Josh Jung", "TEX", Handedness.R, 3, 14, 5.2, tags=["Everyday Bat"]),
        Batter("Brandon Nimmo", "TEX", Handedness.L, 4, 14, 4.2, tags=["Everyday Bat"]),
        Batter("Ezequiel Duran", "TEX", Handedness.R, 5, 5, 4.4, tags=["Lineup Role"]),
        Batter("Jake Burger", "TEX", Handedness.R, 6, 16, 4.9, tags=["Power Threat"]),
        Batter("Evan Carter", "TEX", Handedness.L, 7, 13, 3.5, tags=["YPI", "Lineup Role"]),
        Batter("Elias Diaz", "TEX", Handedness.R, 8, 17, 4.4, tags=["Catcher", "Lineup Role"]),
        Batter("Nicky Lopez", "TEX", Handedness.L, 9, 14, 4.9, tags=["Small Sample"]),
        Batter("Carter Jensen", "KC", Handedness.L, 1, 22, 4.1, tags=["YPI", "Catcher", "Everyday Bat"]),
        Batter("Bobby Witt Jr.", "KC", Handedness.R, 2, 19, 4.9, tags=["Superstar", "5-Tool Star"]),
        Batter("Vinnie Pasquantino", "KC", Handedness.L, 3, 18, 5.9, tags=["Everyday Bat"]),
        Batter("Jac Caglianone", "KC", Handedness.L, 4, 17, 4.9, tags=["YPI", "Lineup Role"]),
        Batter("Lane Thomas", "KC", Handedness.R, 5, 13, 5.1, tags=["Struggling"]),
        Batter("Michael Massey", "KC", Handedness.L, 6, 17, 4.7, tags=["Lineup Role"]),
        Batter("Kameron Misner", "KC", Handedness.L, 7, 11, 5.0, tags=["Lineup Role"]),
        Batter("Nick Loftin", "KC", Handedness.R, 8, 9, 5.3, tags=["Lineup Role"]),
        Batter("Isaac Collins", "KC", Handedness.S, 9, 6, 5.8, tags=["Everyday Bat"]),
    ]
    weak = [PitcherWeakSpot("Michael Wacha", "4-Seam", weakness_score=6), PitcherWeakSpot("Kumar Rocker", "Slider", weakness_score=6)]
    matchups = [HRMatchup("Corey Seager", "Michael Wacha", "4-Seam", 7, exit_velo=105, distance=405)]
    return Game(env.game_id, env, away_p, home_p, batters, weak, matchups)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="Run sample TEX@KC report")
    parser.add_argument("--out", default="data/outputs/sample_report.md")
    args = parser.parse_args()
    if args.sample:
        game = sample_game()
        scores = score_game(game)
        slips = build_slips(scores)
        text = "\n\n".join([step2_report(game), step3_report(game), step4_report(game), step5_report(slips)])
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
