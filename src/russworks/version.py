from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VERSION = "1.0.0"
RELEASE_NAME = "Russ-Works HR Engine V1 Release Candidate"
BUILD_PHASE = "Phase 39"
BUILD_DATE = "2026-06-13"
REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class BuildMetadata:
    version: str = VERSION
    release_name: str = RELEASE_NAME
    build_phase: str = BUILD_PHASE
    build_date: str = BUILD_DATE
    report_schema_version: str = REPORT_SCHEMA_VERSION
    notes: list[str] = field(
        default_factory=lambda: [
            "V1 release candidate metadata.",
            "Formula scores, weights, and slip logic are unchanged in Phase 39.",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_build_metadata() -> dict[str, Any]:
    return BuildMetadata().to_dict()
