from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.deployment import DeploymentConfig, ProviderRuntimeConfig, run_scheduler_from_env
from russworks.scheduler import (
    ScheduledTask,
    SchedulerEngine,
    SchedulerStatus,
    TaskKind,
    TaskResult,
    TaskStatus,
)


DATE = "2026-06-13"


def _handler(status: TaskStatus = TaskStatus.SUCCESS, *, output_path: str = ""):
    def run(task: ScheduledTask, date: str) -> TaskResult:
        return TaskResult(
            task=task,
            status=status,
            started_at=f"{date}T00:00:00Z",
            finished_at=f"{date}T00:00:01Z",
            last_run=f"{date}T00:00:00Z",
            next_run=f"{date}T00:00:00Z",
            output_path=output_path,
            messages=[f"{task.name} handled."],
            errors=["boom"] if status == TaskStatus.FAILED else [],
        )

    return run


def test_phase37_scheduler_models_are_dataclasses():
    assert is_dataclass(ScheduledTask)
    assert is_dataclass(TaskResult)
    assert is_dataclass(SchedulerStatus)


def test_scheduler_runs_supported_tasks_tracks_status_and_exports_json():
    task = ScheduledTask("Pre-slate", TaskKind.PRE_SLATE_RUN, "10:00")
    with TemporaryDirectory() as temp_dir:
        status = SchedulerEngine(task_handlers={TaskKind.PRE_SLATE_RUN: _handler(output_path="report.json")}).run_schedule(
            DATE,
            tasks=[task],
            output_dir=temp_dir,
        )
        payload = json.loads((Path(temp_dir) / "scheduler_status.json").read_text(encoding="utf-8"))

    assert status.success
    assert status.tasks[0].status == TaskStatus.SUCCESS
    assert status.tasks[0].output_path == "report.json"
    assert status.tasks[0].last_run
    assert status.tasks[0].next_run.endswith("Z")
    assert payload["tasks"][0]["task"]["kind"] == "pre_slate_run"


def test_scheduler_tracks_failures_and_retries():
    task = ScheduledTask("Midday", TaskKind.MIDDAY_REFRESH, "15:00", retry_limit=2)
    status = SchedulerEngine(task_handlers={TaskKind.MIDDAY_REFRESH: _handler(TaskStatus.FAILED)}).run_schedule(
        DATE,
        tasks=[task],
    )

    assert not status.success
    assert status.tasks[0].status == TaskStatus.FAILED
    assert status.tasks[0].failures == 3
    assert status.tasks[0].retries == 2
    assert status.errors


def test_scheduler_status_integrates_with_dashboard_and_command_center():
    tasks = [
        ScheduledTask("Dashboard refresh", TaskKind.DASHBOARD_REFRESH, "05:15"),
        ScheduledTask("Recommendation refresh", TaskKind.RECOMMENDATION_REFRESH, "05:30"),
    ]
    status = SchedulerEngine(
        task_handlers={
            TaskKind.DASHBOARD_REFRESH: _handler(output_path="data/dashboard/dashboard.json"),
            TaskKind.RECOMMENDATION_REFRESH: _handler(output_path="data/recommendations/recommendations.json"),
        }
    ).run_schedule(DATE, tasks=tasks)

    dashboard = CalibrationDashboardEngine().build_dashboard(scheduler_status=status)
    command_center = CommandCenterEngine().build_report(date=DATE, scheduler_status=status)

    assert dashboard.scheduler_summaries
    assert command_center.formula_health.scheduler_summary["task_count"] == 2
    assert "data/scheduler/scheduler_status.json" in command_center.execution_summary.exports_generated


def test_deployment_runtime_can_run_scheduler_from_env_with_disabled_task_validation():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        status = run_scheduler_from_env(
            {
                "RUSSWORKS_RUN_DATE": DATE,
                "RUSSWORKS_DATA_ROOT": str(root / "daily"),
                "RUSSWORKS_OUTPUT_ROOT": str(root / "outputs"),
                "RUSSWORKS_CONFIG_PATH": str(root / "missing.yaml"),
                "RUSSWORKS_REPORT_VOLUME": str(root / "data"),
            }
        )

        assert (root / "data" / "scheduler" / "scheduler_status.json").exists()
        assert status.tasks
        assert any(task.task.kind == TaskKind.END_OF_DAY_POSTMORTEM for task in status.tasks)


def test_scheduler_pipeline_task_uses_deployment_config_paths():
    task = ScheduledTask("Pre-slate", TaskKind.PRE_SLATE_RUN, "10:00")
    config = DeploymentConfig(
        date=DATE,
        data_root="daily-root",
        output_root="output-root",
        config_path="config-path",
        provider=ProviderRuntimeConfig(mode="csv"),
    )
    captured = {}

    class FakePipeline:
        def run_daily_pipeline(self, date, request):
            captured["date"] = date
            captured["request"] = request

            class Result:
                success = True
                validation_status = "valid"
                report_json_path = "output-root/report.json"
                errors = []

            return Result()

    status = SchedulerEngine(pipeline=FakePipeline()).run_schedule(DATE, tasks=[task], deployment_config=config)

    assert status.success
    assert captured["request"].data_root == "daily-root"
    assert captured["request"].output_root == "output-root"
    assert captured["request"].config_path == "config-path"
