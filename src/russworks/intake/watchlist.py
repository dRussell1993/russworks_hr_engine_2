from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .batter import BatterIntake
from .game import GameIntake


@dataclass(frozen=True)
class WatchlistImport:
    games: List[GameIntake] = field(default_factory=list)
    batters: List[BatterIntake] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def total_games(self) -> int:
        return len(self.games)

    @property
    def total_watchlist_batters(self) -> int:
        return len(self.batters)
