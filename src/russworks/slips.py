from __future__ import annotations

from typing import List

from .models import BatterScore, Slip


def build_slips(scores: List[BatterScore]) -> List[Slip]:
    ranked = sorted(scores, key=lambda s: s.final_score, reverse=True)
    gold = [s for s in ranked if s.tier.value == "Gold"]
    non_super = [s for s in ranked if "Superstar" not in s.board and s.final_score >= 65]
    ypi = [s for s in ranked if "YPI" in s.board]
    catcher = [s for s in ranked if "Catcher" in s.board]

    slips: List[Slip] = []
    if len(gold) >= 3:
        slips.append(Slip("Formula Alpha", [s.batter.name for s in gold[:3]], "A+", "Core", "Top three total Russ-Works scores."))
    if len(non_super) >= 3:
        slips.append(Slip("Non-Superstar Core", [s.batter.name for s in non_super[:3]], "A", "Value", "High-score bats without superstar tax."))
    if len(ypi) >= 3:
        slips.append(Slip("YPI Special", [s.batter.name for s in ypi[:3]], "A", "YPI", "Young Power Index concentration."))
    if len(catcher) >= 3:
        slips.append(Slip("Catcher Chaos", [s.batter.name for s in catcher[:3]], "B+", "Catcher", "Catcher Power module stack."))
    if len(gold) >= 4:
        slips.append(Slip("Ladder 4-Leg", [s.batter.name for s in gold[:4]], "A", "Ladder", "Top four core targets."))
    return slips
