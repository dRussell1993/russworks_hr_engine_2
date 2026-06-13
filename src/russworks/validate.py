from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from importlib import import_module
import json
from typing import Any, Callable

from russworks.configuration import ConfigLoader
from russworks.reports import REPORT_SCHEMA_VERSION, ReportContext, ReportGenerator
from russworks.scheduler import SchedulerEngine
from russworks.version import VERSION, get_build_metadata


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    success: bool
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseValidationResult:
    success: bool
    version: str
    build_metadata: dict[str, Any]
    checks: list[ValidationCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "version": self.version,
            "build_metadata": dict(self.build_metadata),
            "checks": [asdict(check) for check in self.checks],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def run_validation(config_path: str = "config/russworks_config.yaml") -> ReleaseValidationResult:
    checks = [
        _run_check("imports", _verify_imports),
        _run_check("config_loading", lambda: _verify_config_loading(config_path)),
        _run_check("scheduler_loading", _verify_scheduler_loading),
        _run_check("provider_registration", _verify_provider_registration),
        _run_check("report_generation", _verify_report_generation),
    ]
    return ReleaseValidationResult(
        success=all(check.success for check in checks),
        version=VERSION,
        build_metadata=get_build_metadata(),
        checks=checks,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Russ-Works V1 startup self-tests.")
    parser.add_argument("--config", default="config/russworks_config.yaml", help="Path to the Russ-Works user config file.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    args = parser.parse_args(argv)
    result = run_validation(args.config)
    print(result.to_json(indent=None if args.compact else 2))
    return 0 if result.success else 1


def _run_check(name: str, fn: Callable[[], dict[str, Any]]) -> ValidationCheck:
    try:
        metadata = fn()
    except Exception as exc:
        return ValidationCheck(name=name, success=False, message=str(exc), metadata={})
    return ValidationCheck(name=name, success=True, message="ok", metadata=metadata)


def _verify_imports() -> dict[str, Any]:
    modules = [
        "russworks.automation",
        "russworks.command_center",
        "russworks.configuration",
        "russworks.dashboard",
        "russworks.deployment",
        "russworks.pipeline",
        "russworks.providers",
        "russworks.reports",
        "russworks.scheduler",
        "russworks.web",
    ]
    for module in modules:
        import_module(module)
    return {"modules": modules}


def _verify_config_loading(config_path: str) -> dict[str, Any]:
    config = ConfigLoader(config_path).load()
    return {
        "source_path": config.source_path,
        "risk_profile": config.risk_profile.profile,
        "max_slips": config.slip_preferences.max_slips,
        "legs_per_slip": config.slip_preferences.legs_per_slip,
    }


def _verify_scheduler_loading() -> dict[str, Any]:
    tasks = SchedulerEngine().default_tasks()
    if len(tasks) < 6:
        raise RuntimeError("Scheduler default task set is incomplete.")
    return {"task_count": len(tasks), "tasks": [task.kind.value for task in tasks]}


def _verify_provider_registration() -> dict[str, Any]:
    providers = import_module("russworks.providers")
    expected = {
        "MLBStatsProvider",
        "BaseballSavantProvider",
        "WeatherProvider",
        "BallparkProvider",
        "DailySlateProvider",
        "ProviderResult",
        "ProviderHealth",
    }
    exported = set(getattr(providers, "__all__", []))
    missing = sorted(expected - exported)
    if missing:
        raise RuntimeError(f"Provider exports missing: {', '.join(missing)}")
    return {"registered": sorted(expected)}


def _verify_report_generation() -> dict[str, Any]:
    context = ReportContext(
        report_date="1970-01-01",
        games_reviewed=0,
        validation_status="self_test",
        notes=["Release validation self-test."],
        active_config={"source": "self_test"},
    )
    report = ReportGenerator().generate_full_report(
        context=context,
        step3_results=None,
        cluster_ranking=None,
        slip_portfolio=None,
    )
    payload = report.to_dict()
    if payload.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise RuntimeError("Generated report schema version mismatch.")
    for section in ("context", "step3", "step4", "step5"):
        if section not in payload:
            raise RuntimeError(f"Generated report missing {section}.")
    return {"schema_version": payload["schema_version"], "sections": ["context", "step3", "step4", "step5"]}


if __name__ == "__main__":
    raise SystemExit(main())
