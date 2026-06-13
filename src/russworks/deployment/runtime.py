from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
from typing import Mapping

from russworks.configuration import ConfigLoader
from russworks.pipeline import DailyRunRequest, RussWorksPipeline

from .models import (
    DeploymentConfig,
    DeploymentValidationResult,
    ProviderRuntimeConfig,
    RuntimeExecutionResult,
    RuntimeMode,
    ScheduleConfig,
)


def config_from_env(env: Mapping[str, str] | None = None) -> DeploymentConfig:
    values = env or os.environ
    return DeploymentConfig(
        runtime_mode=_runtime_mode(values.get("RUSSWORKS_RUNTIME_MODE", "local")),
        date=values.get("RUSSWORKS_RUN_DATE", ""),
        data_root=values.get("RUSSWORKS_DATA_ROOT", "data/daily"),
        output_root=values.get("RUSSWORKS_OUTPUT_ROOT", "data/outputs"),
        config_path=values.get("RUSSWORKS_CONFIG_PATH", "config/russworks_config.yaml"),
        report_volume=values.get("RUSSWORKS_REPORT_VOLUME", "data"),
        provider=ProviderRuntimeConfig(
            mode=values.get("RUSSWORKS_PROVIDER_MODE", "csv"),
            mlb_stats_base_url=values.get("RUSSWORKS_MLB_STATS_BASE_URL", ""),
            baseball_savant_base_url=values.get("RUSSWORKS_BASEBALL_SAVANT_BASE_URL", ""),
            weather_base_url=values.get("RUSSWORKS_WEATHER_BASE_URL", ""),
            ballpark_base_url=values.get("RUSSWORKS_BALLPARK_BASE_URL", ""),
            provider_timeout_seconds=_float(values.get("RUSSWORKS_PROVIDER_TIMEOUT_SECONDS", "10"), 10.0),
            provider_max_retries=_int(values.get("RUSSWORKS_PROVIDER_MAX_RETRIES", "2"), 2),
        ),
        schedule=ScheduleConfig(
            enabled=_bool(values.get("RUSSWORKS_SCHEDULE_ENABLED", "false")),
            daily_run_time_utc=values.get("RUSSWORKS_DAILY_RUN_TIME_UTC", "15:00"),
            timezone=values.get("RUSSWORKS_TIMEZONE", "UTC"),
        ),
    )


def validate_runtime_config(config: DeploymentConfig) -> DeploymentValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    checked_paths = {
        "data_root": config.data_root,
        "output_root": config.output_root,
        "config_path": config.config_path,
        "report_volume": config.report_volume,
    }
    if config.provider.mode not in {"csv", "live"}:
        errors.append("RUSSWORKS_PROVIDER_MODE must be csv or live.")
    if config.provider.mode == "live" and not any(
        [
            config.provider.mlb_stats_base_url,
            config.provider.baseball_savant_base_url,
            config.provider.weather_base_url,
            config.provider.ballpark_base_url,
        ]
    ):
        warnings.append("Live provider mode is enabled but no provider base URLs are configured; CSV fallback may be required.")
    if not Path(config.config_path).exists():
        warnings.append(f"Config file not found; default config will be used: {config.config_path}")
    else:
        try:
            ConfigLoader(config.config_path).load()
        except Exception as exc:
            errors.append(f"Configuration loading failed: {exc}")
    if not Path(config.data_root).exists():
        warnings.append(f"Data root does not exist yet: {config.data_root}")
    Path(config.output_root).mkdir(parents=True, exist_ok=True)
    Path(config.report_volume).mkdir(parents=True, exist_ok=True)
    return DeploymentValidationResult(success=not errors, errors=errors, warnings=warnings, checked_paths=checked_paths)


def run_daily_from_env(env: Mapping[str, str] | None = None) -> RuntimeExecutionResult:
    config = config_from_env(env)
    validation = validate_runtime_config(config)
    if not validation.success:
        return RuntimeExecutionResult(success=False, config=config, validation=validation, errors=list(validation.errors))
    run_date = config.date or _today()
    request = DailyRunRequest(
        date=run_date,
        data_root=config.data_root,
        output_root=config.output_root,
        provider_mode=config.provider.mode,
        config_path=config.config_path,
    )
    result = RussWorksPipeline().run_daily_pipeline(run_date, request)
    return RuntimeExecutionResult(
        success=result.success,
        config=config,
        validation=validation,
        pipeline_result={
            "success": result.success,
            "date": result.request.date,
            "validation_status": result.validation_status,
            "total_batters_reviewed": result.total_batters_reviewed,
            "output_dir": result.output_dir,
            "report_json_path": result.report_json_path,
            "errors": list(result.errors),
            "missing_data": dict(result.missing_data),
        },
        messages=["Daily pipeline executed from deployment runtime."],
        errors=list(result.errors),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Russ-Works deployment runtime helper.")
    parser.add_argument("--validate-only", action="store_true", help="Validate container runtime configuration without running the pipeline.")
    args = parser.parse_args(argv)
    config = config_from_env()
    if args.validate_only:
        validation = validate_runtime_config(config)
        print(RuntimeExecutionResult(success=validation.success, config=config, validation=validation, errors=list(validation.errors)).to_json())
        return 0 if validation.success else 1
    result = run_daily_from_env()
    print(result.to_json())
    return 0 if result.success else 1


def _runtime_mode(value: str) -> RuntimeMode:
    normalized = str(value).strip().lower()
    return RuntimeMode.PRODUCTION if normalized == RuntimeMode.PRODUCTION.value else RuntimeMode.LOCAL


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _today() -> str:
    return datetime.utcnow().date().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
