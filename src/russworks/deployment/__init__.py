"""Deployment runtime exports."""

from russworks.deployment.models import (
    DeploymentConfig,
    DeploymentValidationResult,
    ProviderRuntimeConfig,
    RuntimeExecutionResult,
    RuntimeMode,
    ScheduleConfig,
)


def config_from_env(*args, **kwargs):
    from russworks.deployment.runtime import config_from_env as _config_from_env

    return _config_from_env(*args, **kwargs)


def run_daily_from_env(*args, **kwargs):
    from russworks.deployment.runtime import run_daily_from_env as _run_daily_from_env

    return _run_daily_from_env(*args, **kwargs)


def validate_runtime_config(*args, **kwargs):
    from russworks.deployment.runtime import validate_runtime_config as _validate_runtime_config

    return _validate_runtime_config(*args, **kwargs)

__all__ = [
    "DeploymentConfig",
    "DeploymentValidationResult",
    "ProviderRuntimeConfig",
    "RuntimeExecutionResult",
    "RuntimeMode",
    "ScheduleConfig",
    "config_from_env",
    "run_daily_from_env",
    "validate_runtime_config",
]
