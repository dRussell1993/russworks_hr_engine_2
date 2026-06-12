from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .models import BatterScore, Game, PostMortemEntry, Slip, TeamClusterScore
from .scoring import calculate_team_clusters, score_game
from .validation import validate_step2


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def step2_report(game: Game) -> str:
    env = game.environment
    rows = [
        ["Game", f"{env.away_team} @ {env.home_team}"],
        ["Park", env.park],
        ["Weather HR%", env.weather_hr_pct],
        ["Weather Feet", env.weather_distance_ft],
        ["Wind", f"{env.wind_mph} {env.wind_direction}"],
        ["Roof", env.roof],
        ["Umpire", env.umpire.name if env.umpire else ""],
        ["Away Pitcher", game.away_pitcher.name],
        ["Home Pitcher", game.home_pitcher.name],
    ]
    return "# STEP 2 — Game Confirmation\n\n" + md_table(["Field", "Value"], rows)


def step3_report(game: Game) -> str:
    validate_step2(game)
    clusters = calculate_team_clusters(game)
    scores = score_game(game)
    by_team: Dict[str, List[BatterScore]] = defaultdict(list)
    for s in scores:
        by_team[s.batter.team].append(s)

    lines = [f"# STEP 3 — FULL RUSS-WORKS REPORT", f"## Game: {game.environment.away_team} @ {game.environment.home_team}", "All batters reviewed. No shortcuts."]
    for team in [game.environment.away_team, game.environment.home_team]:
        opp = game.home_pitcher if team == game.environment.away_team else game.away_pitcher
        lines.append(f"\n## {team} vs {opp.name}\n")
        rows = []
        for s in sorted(by_team[team], key=lambda x: x.batter.lineup_slot):
            rows.append([
                s.batter.name,
                s.batter.lineup_slot,
                f"{s.batter.hr_pct:g}%",
                s.board,
                f"{s.lpas:g}",
                f"{s.pitcher_collision:g}",
                f"{s.final_score:g}",
                s.tier.value,
            ])
        lines.append(md_table(["Batter", "Slot", "HR%", "Board", "LPAS", "Collision", "Final", "Russ"], rows))
        c = clusters[team]
        lines.append(f"\n**{team} TAG:** {c.tag_grade} ({c.tag_score})  ")
        lines.append(f"**{team} CPS:** {c.cps_grade} ({c.cps_score})  ")
        lines.append(f"**Cluster Core:** {', '.join(c.core_batters)}")

    gold = sorted([s for s in scores if s.tier.value == "Gold"], key=lambda x: x.final_score, reverse=True)
    silver = sorted([s for s in scores if s.tier.value == "Silver"], key=lambda x: x.final_score, reverse=True)
    bronze = sorted([s for s in scores if s.tier.value == "Bronze"], key=lambda x: x.final_score, reverse=True)

    lines.append("\n# STEP 3 GOLD POOL\n")
    lines.append(md_table(["Rank", "Batter", "Team", "Score", "Why"], [[i+1, s.batter.name, s.batter.team, s.final_score, s.board] for i, s in enumerate(gold)]))
    lines.append("\n# SILVER POOL\n")
    lines.append(md_table(["Batter", "Team", "Score"], [[s.batter.name, s.batter.team, s.final_score] for s in silver]))
    lines.append("\n# BRONZE / CHAOS POOL\n")
    lines.append(md_table(["Batter", "Team", "Score"], [[s.batter.name, s.batter.team, s.final_score] for s in bronze]))
    return "\n".join(lines)


def step4_report(game: Game) -> str:
    validate_step2(game)
    clusters = calculate_team_clusters(game)
    rows = []
    for c in sorted(clusters.values(), key=lambda x: x.cluster_score, reverse=True):
        rows.append([c.team, c.tag_grade, c.tag_score, c.cps_grade, c.cps_score, c.cluster_score, ", ".join(c.core_batters)])
    return "# STEP 4 — TAG / CPS Cluster Construction\n\n" + md_table(["Team", "TAG", "TAG Score", "CPS", "CPS Score", "Cluster", "Core"], rows)


def step5_report(slips: List[Slip]) -> str:
    rows = [[s.name, s.slip_type, ", ".join(s.batters), s.grade, s.rationale] for s in slips]
    return "# STEP 5 — Slip Construction\n\n" + md_table(["Slip", "Type", "Batters", "Grade", "Why"], rows)


def postmortem_report(entries: List[PostMortemEntry]) -> str:
    winners = [e for e in entries if e.result.lower() == "winner"]
    losers = [e for e in entries if e.result.lower() == "loser"]
    false_pos = [e for e in entries if e.result.lower() == "false_positive"]
    lines = ["# POST-MORTEM REPORT", ""]
    lines.append("## Winners Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Pitch", "Pitcher", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.pitch or "", e.pitcher or "", e.notes] for e in winners]))
    lines.append("\n## Losers Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.notes] for e in losers]))
    lines.append("\n## False Positive Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.notes] for e in false_pos]))
    return "\n".join(lines)
