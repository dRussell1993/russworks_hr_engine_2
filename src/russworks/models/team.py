from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .batter import Handedness


@dataclass
class Pitcher:
    name: str
    team: str
    throws: Handedness = Handedness.UNKNOWN
    tags: List[str] = field(default_factory=list)
    projected_ip: float = 0.0
    projected_hits: float = 0.0
    projected_hr: float = 0.0
    projected_bb: float = 0.0
    projected_er: float = 0.0
    projected_outs: float = 0.0
