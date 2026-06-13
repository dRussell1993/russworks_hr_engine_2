from __future__ import annotations

from pathlib import Path

from russworks.validate import main, run_validation
from russworks.version import VERSION, get_build_metadata


def test_version_metadata_is_v1_release_candidate():
    metadata = get_build_metadata()

    assert VERSION == "1.0.0"
    assert metadata["version"] == "1.0.0"
    assert metadata["build_phase"] == "Phase 39"


def test_release_validation_succeeds():
    result = run_validation()

    assert result.success is True
    assert {check.name for check in result.checks} == {
        "imports",
        "config_loading",
        "scheduler_loading",
        "provider_registration",
        "report_generation",
    }


def test_release_validation_cli_returns_zero():
    assert main(["--compact"]) == 0


def test_v1_release_document_contains_required_sections():
    text = Path("RUSSWORKS_V1_RELEASE.md").read_text(encoding="utf-8")

    required_sections = [
        "Final Architecture Overview",
        "Completed Phases 1-38",
        "Module Dependency Map",
        "Daily Operator Workflow",
        "Required Daily Inputs",
        "Generated Outputs",
        "Deployment Guide",
        "Scheduler Guide",
        "Post-Mortem Guide",
        "Troubleshooting Guide",
        "Recovery Procedures",
        "Provider Configuration Guide",
        "Validation Checklist",
        "Known Limitations",
        "Future Roadmap",
    ]
    for section in required_sections:
        assert section in text
