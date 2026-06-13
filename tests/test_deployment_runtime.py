from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.deployment import (
    DeploymentConfig,
    DeploymentValidationResult,
    ProviderRuntimeConfig,
    RuntimeExecutionResult,
    RuntimeMode,
    ScheduleConfig,
    config_from_env,
    run_daily_from_env,
    validate_runtime_config,
)

from tests.test_daily_pipeline import _write_daily_csv_fixture


DATE = "2026-06-13"


def test_phase36_deployment_models_are_dataclasses():
    assert is_dataclass(ProviderRuntimeConfig)
    assert is_dataclass(ScheduleConfig)
    assert is_dataclass(DeploymentConfig)
    assert is_dataclass(DeploymentValidationResult)
    assert is_dataclass(RuntimeExecutionResult)


def test_config_from_env_supports_runtime_provider_schedule_and_mounts():
    config = config_from_env(
        {
            "RUSSWORKS_RUNTIME_MODE": "production",
            "RUSSWORKS_RUN_DATE": DATE,
            "RUSSWORKS_PROVIDER_MODE": "live",
            "RUSSWORKS_DATA_ROOT": "/app/data/daily",
            "RUSSWORKS_OUTPUT_ROOT": "/app/data/outputs",
            "RUSSWORKS_CONFIG_PATH": "/app/config/russworks_config.yaml",
            "RUSSWORKS_REPORT_VOLUME": "/app/data",
            "RUSSWORKS_MLB_STATS_BASE_URL": "https://example.test/mlb",
            "RUSSWORKS_SCHEDULE_ENABLED": "true",
            "RUSSWORKS_DAILY_RUN_TIME_UTC": "16:30",
        }
    )

    assert config.runtime_mode == RuntimeMode.PRODUCTION
    assert config.provider.mode == "live"
    assert config.provider.mlb_stats_base_url == "https://example.test/mlb"
    assert config.schedule.enabled
    assert config.schedule.daily_run_time_utc == "16:30"


def test_validate_runtime_config_loads_config_and_prepares_output_paths():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        report_volume = root / "reports"
        config_path = root / "config" / "russworks_config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(
            "\n".join(
                [
                    "slip_preferences:",
                    "  max_slips: 12",
                    "  legs_per_slip: 4",
                    "risk_profile:",
                    "  profile: balanced",
                ]
            ),
            encoding="utf-8",
        )
        config = DeploymentConfig(
            date=DATE,
            data_root=str(data_root),
            output_root=str(output_root),
            config_path=str(config_path),
            report_volume=str(report_volume),
        )

        result = validate_runtime_config(config)

        assert result.success
        assert output_root.exists()
        assert report_volume.exists()
        assert result.checked_paths["config_path"] == str(config_path)


def test_deployment_runtime_executes_pipeline_and_generates_report():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_root = root / "daily"
        output_root = root / "outputs"
        config_path = root / "missing_config.yaml"
        _write_daily_csv_fixture(data_root, DATE)

        result = run_daily_from_env(
            {
                "RUSSWORKS_RUN_DATE": DATE,
                "RUSSWORKS_PROVIDER_MODE": "csv",
                "RUSSWORKS_DATA_ROOT": str(data_root),
                "RUSSWORKS_OUTPUT_ROOT": str(output_root),
                "RUSSWORKS_CONFIG_PATH": str(config_path),
                "RUSSWORKS_REPORT_VOLUME": str(root / "data"),
            }
        )

        assert result.success
        assert result.pipeline_result["report_json_path"] == str(output_root / DATE / "russworks_full_report.json")
        assert Path(result.pipeline_result["report_json_path"]).exists()

        payload = json.loads(result.to_json())
        assert payload["config"]["date"] == DATE
        assert payload["validation"]["warnings"]
