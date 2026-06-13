from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping, Sequence

from russworks.automation import AutoPostMortemRunner, DailyPostMortemRun
from russworks.command_center import CommandCenterEngine, CommandCenterReport
from russworks.dashboard import CalibrationDashboardEngine
from russworks.deployment import DeploymentConfig
from russworks.pipeline import DailyRunRequest, DailyRunResult, RussWorksPipeline
from russworks.recommendations import WeightRecommendationEngine

from .models import ScheduledTask, SchedulerStatus, TaskKind, TaskResult, TaskStatus


TaskHandler = Callable[[ScheduledTask, str], TaskResult]


class SchedulerEngine:
    def __init__(
        self,
        *,
        pipeline: RussWorksPipeline | None = None,
        postmortem_runner: AutoPostMortemRunner | None = None,
        command_center: CommandCenterEngine | None = None,
        task_handlers: Mapping[TaskKind, TaskHandler] | None = None,
    ) -> None:
        self.pipeline = pipeline or RussWorksPipeline()
        self.postmortem_runner = postmortem_runner or AutoPostMortemRunner()
        self.command_center = command_center or CommandCenterEngine()
        self.task_handlers = dict(task_handlers or {})
        self.last_daily_result: DailyRunResult | None = None
        self.last_command_center_report: CommandCenterReport | None = None

    def default_tasks(self) -> list[ScheduledTask]:
        return [
            ScheduledTask("Pre-slate run", TaskKind.PRE_SLATE_RUN, "10:00"),
            ScheduledTask("Midday refresh", TaskKind.MIDDAY_REFRESH, "15:00"),
            ScheduledTask("Lineup confirmation refresh", TaskKind.LINEUP_CONFIRMATION_REFRESH, "20:00"),
            ScheduledTask("End-of-day post-mortem", TaskKind.END_OF_DAY_POSTMORTEM, "05:00"),
            ScheduledTask("Dashboard refresh", TaskKind.DASHBOARD_REFRESH, "05:15"),
            ScheduledTask("Recommendation refresh", TaskKind.RECOMMENDATION_REFRESH, "05:30"),
        ]

    def run_schedule(
        self,
        date: str,
        *,
        tasks: Sequence[ScheduledTask] | None = None,
        deployment_config: DeploymentConfig | None = None,
        output_dir: str | Path = "data/scheduler",
    ) -> SchedulerStatus:
        task_list = list(tasks or self.default_tasks())
        results = [self.run_task(task, date, deployment_config=deployment_config) for task in task_list]
        status = SchedulerStatus(
            generated_at=_now(),
            date=date,
            tasks=results,
            errors=[error for result in results for error in result.errors if result.status == TaskStatus.FAILED],
        )
        self.export_json(status, output_dir)
        return status

    def run_task(
        self,
        task: ScheduledTask,
        date: str,
        *,
        deployment_config: DeploymentConfig | None = None,
    ) -> TaskResult:
        if not task.enabled:
            return _task_result(task, TaskStatus.SKIPPED, date, messages=["Task is disabled."])
        handler = self.task_handlers.get(task.kind) or self._default_handler(task.kind, deployment_config)
        failures = 0
        retries = 0
        last_error: list[str] = []
        for attempt in range(task.retry_limit + 1):
            result = handler(task, date)
            if result.status != TaskStatus.FAILED:
                return result
            failures += 1
            last_error = list(result.errors)
            if attempt < task.retry_limit:
                retries += 1
                continue
            return _task_result(
                task,
                TaskStatus.FAILED,
                date,
                failures=failures,
                retries=retries,
                errors=last_error or ["Task failed."],
            )
        return _task_result(task, TaskStatus.FAILED, date, failures=failures, retries=retries, errors=last_error)

    def export_json(self, status: SchedulerStatus, output_dir: str | Path = "data/scheduler") -> Path:
        output_path = Path(output_dir) / "scheduler_status.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(status.to_json(), encoding="utf-8")
        return output_path

    def _default_handler(
        self,
        task_kind: TaskKind,
        deployment_config: DeploymentConfig | None,
    ) -> TaskHandler:
        if task_kind in {TaskKind.PRE_SLATE_RUN, TaskKind.MIDDAY_REFRESH, TaskKind.LINEUP_CONFIRMATION_REFRESH}:
            return lambda task, date: self._run_pipeline_task(task, date, deployment_config=deployment_config)
        if task_kind == TaskKind.END_OF_DAY_POSTMORTEM:
            return self._run_postmortem_task
        if task_kind == TaskKind.DASHBOARD_REFRESH:
            return self._run_dashboard_task
        if task_kind == TaskKind.RECOMMENDATION_REFRESH:
            return self._run_recommendation_task
        return lambda task, date: _task_result(task, TaskStatus.SKIPPED, date, messages=["No scheduler handler configured."])

    def _run_pipeline_task(
        self,
        task: ScheduledTask,
        date: str,
        *,
        deployment_config: DeploymentConfig | None,
    ) -> TaskResult:
        request = _daily_request(date, deployment_config)
        result = self.pipeline.run_daily_pipeline(date, request)
        self.last_daily_result = result
        return _task_result(
            task,
            TaskStatus.SUCCESS if result.success else TaskStatus.FAILED,
            date,
            output_path=result.report_json_path,
            messages=[f"{task.name} pipeline run completed with validation status {result.validation_status}."],
            errors=list(result.errors),
        )

    def _run_postmortem_task(self, task: ScheduledTask, date: str) -> TaskResult:
        result = self.postmortem_runner.run_postmortem(date, DailyPostMortemRun(date=date))
        status = TaskStatus.SKIPPED if result.skipped else (TaskStatus.SUCCESS if result.success else TaskStatus.FAILED)
        return _task_result(
            task,
            status,
            date,
            output_path=result.postmortem_report_path or result.metadata_path,
            messages=list(result.messages),
            errors=list(result.errors),
        )

    def _run_dashboard_task(self, task: ScheduledTask, date: str) -> TaskResult:
        dashboard = CalibrationDashboardEngine().build_dashboard(
            portfolio_profile=self.last_daily_result.portfolio_report if self.last_daily_result else None,
            diversification_result=self.last_daily_result.diversification_report if self.last_daily_result else None,
            simulation_result=self.last_daily_result.simulation_report if self.last_daily_result else None,
            self_learning_report=self.last_daily_result.self_learning_report if self.last_daily_result else None,
        )
        output_path = CalibrationDashboardEngine().export_json(dashboard, Path("data/dashboard"))
        return _task_result(
            task,
            TaskStatus.SUCCESS if dashboard.success else TaskStatus.FAILED,
            date,
            output_path=str(output_path),
            messages=["Dashboard refresh completed."],
            errors=list(dashboard.errors),
        )

    def _run_recommendation_task(self, task: ScheduledTask, date: str) -> TaskResult:
        dashboard = CalibrationDashboardEngine().build_dashboard()
        recommendations = WeightRecommendationEngine().build_recommendations(dashboard=dashboard)
        output_path = WeightRecommendationEngine().export_json(recommendations, Path("data/recommendations"))
        command_center = self.command_center.build_report(
            date=date,
            daily_run_result=self.last_daily_result,
            dashboard=dashboard,
            recommendations=recommendations,
        )
        self.last_command_center_report = command_center
        self.command_center.export_json(command_center)
        return _task_result(
            task,
            TaskStatus.SUCCESS if recommendations.success else TaskStatus.FAILED,
            date,
            output_path=str(output_path),
            messages=["Recommendation refresh completed."],
            errors=list(recommendations.errors),
        )


def run_schedule(
    date: str,
    *,
    tasks: Sequence[ScheduledTask] | None = None,
    deployment_config: DeploymentConfig | None = None,
    output_dir: str | Path = "data/scheduler",
) -> SchedulerStatus:
    return SchedulerEngine().run_schedule(date, tasks=tasks, deployment_config=deployment_config, output_dir=output_dir)


def _daily_request(date: str, config: DeploymentConfig | None) -> DailyRunRequest:
    if config is None:
        return DailyRunRequest(date=date)
    return DailyRunRequest(
        date=date,
        data_root=config.data_root,
        output_root=config.output_root,
        provider_mode=config.provider.mode,
        config_path=config.config_path,
    )


def _task_result(
    task: ScheduledTask,
    status: TaskStatus,
    date: str,
    *,
    failures: int = 0,
    retries: int = 0,
    output_path: str = "",
    messages: list[str] | None = None,
    errors: list[str] | None = None,
) -> TaskResult:
    started = _now()
    return TaskResult(
        task=task,
        status=status,
        started_at=started,
        finished_at=_now(),
        last_run=started,
        next_run=_next_run(date, task.run_time_utc),
        failures=failures,
        retries=retries,
        output_path=output_path,
        messages=list(messages or []),
        errors=list(errors or []),
    )


def _next_run(date: str, run_time_utc: str) -> str:
    try:
        hour, minute = [int(part) for part in run_time_utc.split(":", 1)]
        base = datetime.fromisoformat(date)
        return (base.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)).isoformat() + "Z"
    except Exception:
        return ""


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
