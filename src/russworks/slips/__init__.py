"""Step 5 slip construction exports."""

from typing import List

from russworks.models import BatterScore, Slip as LegacySlip
from russworks.slips.models import Slip, SlipLeg, SlipPortfolio
from russworks.slips.step5 import (
    Step5SlipEngine,
    generate_balanced_slips,
    generate_chaos_slips,
    generate_contrarian_slips,
    generate_core_slips,
    generate_non_superstar_core_slips,
    generate_slip_portfolio,
)


def build_slips(scores: List[BatterScore]) -> List[LegacySlip]:
    """Backward-compatible slip builder used by the sample report path."""
    ranked = sorted(scores, key=lambda score: score.final_score, reverse=True)
    gold = [score for score in ranked if score.tier.value == "Gold"]
    non_super = [score for score in ranked if "Superstar" not in score.board and score.final_score >= 65]
    ypi = [score for score in ranked if "YPI" in score.board]
    catcher = [score for score in ranked if "Catcher" in score.board]

    slips: List[LegacySlip] = []
    if len(gold) >= 3:
        slips.append(LegacySlip("Formula Alpha", [score.batter.name for score in gold[:3]], "A+", "Core", "Top three total Russ-Works scores."))
    if len(non_super) >= 3:
        slips.append(LegacySlip("Non-Superstar Core", [score.batter.name for score in non_super[:3]], "A", "Value", "High-score bats without superstar tax."))
    if len(ypi) >= 3:
        slips.append(LegacySlip("YPI Special", [score.batter.name for score in ypi[:3]], "A", "YPI", "Young Power Index concentration."))
    if len(catcher) >= 3:
        slips.append(LegacySlip("Catcher Chaos", [score.batter.name for score in catcher[:3]], "B+", "Catcher", "Catcher Power module stack."))
    if len(gold) >= 4:
        slips.append(LegacySlip("Ladder 4-Leg", [score.batter.name for score in gold[:4]], "A", "Ladder", "Top four core targets."))
    return slips


__all__ = [
    "Slip",
    "SlipLeg",
    "SlipPortfolio",
    "Step5SlipEngine",
    "build_slips",
    "generate_balanced_slips",
    "generate_chaos_slips",
    "generate_contrarian_slips",
    "generate_core_slips",
    "generate_non_superstar_core_slips",
    "generate_slip_portfolio",
]
