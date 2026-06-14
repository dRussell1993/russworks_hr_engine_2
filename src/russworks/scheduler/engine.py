from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from russworks.automation import AutoPostMortemRunner, DailyPostMortemRun
from russworks.command_center import CommandCenterEngine, CommandCenterReport
from russworks.dashboard import CalibrationDashboardEngine
from russworks.deployment import DeploymentConfig
from russworks.pipeline import DailyRunRequest, DailyRunResult, RussWorksPipeline
from russworks.recommendations import WeightRecommendationEngine
from russworks.slate import LiveSlateBuilder, ProviderMappingConfig, SlateBuildResult

from .models import ScheduledTask, SchedulerRunHistoryEntry, SchedulerStatus, TaskKind, TaskResult, TaskStatus


TaskHandler = Callable[[ScheduledTask, str], TaskResult]


class SchedulerEngine:
    def __init__(
        self,
        *,
        pipeline: RussWorksPipeline | None = None,
        postmortem_runner: AutoPostMortemRunner | None = None,
        command_center: CommandCenterEngine | None = None,
        slate_builder: LiveSlateBuilder | None = None,
        task_handlers: Mapping[TaskKind, TaskHandler] | None = None,
    ) -> None:
        self.pipeline = pipeline or RussWorksPipeline()
        self.postmortem_runner = postmortem_runner or AutoPostMortemRunner()
        self.command_center = command_center or CommandCenterEngine()
        self.slate_builder = slate_builder
        self.task_handlers = dict(task_handlers or {})
        self.last_daily_result: DailyRunResult | None = None
        self.last_command_center_report: CommandCenterReport | None = None
        self.last_postmortem_result = None
        self.last_slate_build_result: SlateBuildResult | None = None

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
        history = _history_entries(date, results)
        status = SchedulerStatus(
            generated_at=_now(),
            date=date,
            tasks=results,
            history=history,
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
        _append_history(Path(output_dir) / "run_history.json", status.history)
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
        slate_build = self._build_slate_for_task(date, request)
        result = self.pipeline.run_daily_pipeline(date, request)
        self.last_daily_result = result
        metadata = _pipeline_metadata(result)
        if slate_build is not None:
            metadata.update(_slate_metadata(slate_build))
        return _task_result(
            task,
            TaskStatus.SUCCESS if result.success else TaskStatus.FAILED,
            date,
            output_path=result.report_json_path,
            metadata=metadata,
            messages=[
                *([f"Slate generation {'completed' if slate_build and slate_build.success else 'completed with warnings'}: {slate_build.output_dir}"] if slate_build else []),
                f"{task.name} pipeline run completed with validation status {result.validation_status}.",
            ],
            errors=list(result.errors),
        )

    def _run_postmortem_task(self, task: ScheduledTask, date: str) -> TaskResult:
        result = self.postmortem_runner.run_postmortem(date, DailyPostMortemRun(date=date))
        self.last_postmortem_result = result
        status = TaskStatus.SKIPPED if result.skipped else (TaskStatus.SUCCESS if result.success else TaskStatus.FAILED)
        metadata = _postmortem_metadata(result)
        return _task_result(
            task,
            status,
            date,
            output_path=result.postmortem_report_path or result.metadata_path,
            metadata=metadata,
            messages=list(result.messages),
            errors=list(result.errors),
        )

    def _run_dashboard_task(self, task: ScheduledTask, date: str) -> TaskResult:
        dashboard = CalibrationDashboardEngine().build_dashboard(
            portfolio_profile=self.last_daily_result.portfolio_report if self.last_daily_result else None,
            diversification_result=self.last_daily_result.diversification_report if self.last_daily_result else None,
            simulation_result=self.last_daily_result.simulation_report if self.last_daily_result else None,
            self_learning_report=self.last_daily_result.self_learning_report if self.last_daily_result else None,
            postmortem_reports=[self.last_postmortem_result.postmortem_report] if self.last_postmortem_result and self.last_postmortem_result.postmortem_report else (),
            scheduler_status=_transient_status(date, [task], self.last_slate_build_result, self.last_postmortem_result),
        )
        output_path = CalibrationDashboardEngine().export_json(dashboard, Path("data/dashboard"))
        return _task_result(
            task,
            TaskStatus.SUCCESS if dashboard.success else TaskStatus.FAILED,
            date,
            output_path=str(output_path),
            metadata={"dashboard_path": str(output_path)},
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
            metadata={"recommendations": len(recommendations.modules), "recommendations_path": str(output_path)},
            messages=["Recommendation refresh completed."],
            errors=list(recommendations.errors),
        )

    def _build_slate_for_task(self, date: str, request: DailyRunRequest) -> SlateBuildResult | None:
        builder = self.slate_builder or LiveSlateBuilder(
            config=ProviderMappingConfig(data_root=request.data_root)
        )
        try:
            result = builder.build_slate(date)
        except Exception:
            return None
        self.last_slate_build_result = result
        return result


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
    metadata: dict[str, object] | None = None,
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
        metadata=dict(metadata or {}),
        messages=list(messages or []),
        errors=list(errors or []),
    )


def _history_entries(date: str, results: Sequence[TaskResult]) -> list[SchedulerRunHistoryEntry]:
    return [
        SchedulerRunHistoryEntry(
            date=date,
            generated_at=result.finished_at or result.started_at,
            task_name=result.task.name,
            task_kind=result.task.kind.value,
            status=result.status.value,
            output_path=result.output_path,
            metadata=dict(result.metadata),
            messages=list(result.messages),
            errors=list(result.errors),
        )
        for result in results
    ]


def _append_history(path: Path, entries: Sequence[SchedulerRunHistoryEntry]) -> None:
    existing = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                existing = payload
        except json.JSONDecodeError:
            existing = []
    existing.extend(entry.__dict__ for entry in entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


def _pipeline_metadata(result: DailyRunResult) -> dict[str, object]:
    validation_summary = getattr(result, "validation_summary", {}) or {}
    return {
        "last_slate_run": _now(),
        "validation_status": getattr(result, "validation_status", ""),
        "games_reviewed": validation_summary.get("complete_games", 0),
        "report_json_path": getattr(result, "report_json_path", ""),
        "dashboard_path": getattr(result, "dashboard_path", ""),
    }


def _slate_metadata(result: SlateBuildResult) -> dict[str, object]:
    return {
        "slate_output_dir": result.output_dir,
        "slate_generation_success": result.success,
        "slate_generation_partial": result.partial,
        "slate_record_counts": dict(result.record_counts),
        "slate_files_written": dict(result.files_written),
    }


def _postmortem_metadata(result) -> dict[str, object]:
    report = result.postmortem_report
    calibration = result.calibration_result
    return {
        "last_postmortem_run": _now(),
        "last_successful_acquisition": _now() if result.actual_home_runs_loaded else "",
        "hr_events_acquired": result.actual_home_runs_loaded,
        "winners": len(report.winner_log) if report else 0,
        "misses": len(report.loser_log) if report else 0,
        "false_positives": len(report.false_positive_log) if report else 0,
        "adjustments": len(report.adjustment_log) if report else 0,
        "calibration_recommendations": len(calibration.recommended_adjustments) if calibration else 0,
        "postmortem_report_path": result.postmortem_report_path,
        "dashboard_path": result.dashboard_path,
        "recommendations_path": result.recommendations_path,
    }


def _transient_status(date: str, tasks: Sequence[ScheduledTask], slate_build, postmortem_result) -> SchedulerStatus:
    task_results = []
    if slate_build is not None:
        task_results.append(
            _task_result(
                ScheduledTask("Slate generation", TaskKind.PRE_SLATE_RUN, "00:00"),
                TaskStatus.SUCCESS if slate_build.success else TaskStatus.FAILED,
                date,
                output_path=slate_build.output_dir,
                metadata=_slate_metadata(slate_build),
            )
        )
    if postmortem_result is not None:
        task_results.append(
            _task_result(
                ScheduledTask("Post-mortem", TaskKind.END_OF_DAY_POSTMORTEM, "00:00"),
                TaskStatus.SKIPPED if postmortem_result.skipped else (TaskStatus.SUCCESS if postmortem_result.success else TaskStatus.FAILED),
                date,
                output_path=postmortem_result.postmortem_report_path,
                metadata=_postmortem_metadata(postmortem_result),
            )
        )
    task_results.extend(_task_result(task, TaskStatus.PENDING, date) for task in tasks)
    return SchedulerStatus(generated_at=_now(), date=date, tasks=task_results, history=_history_entries(date, task_results))


def _next_run(date: str, run_time_utc: str) -> str:
    try:
        hour, minute = [int(part) for part in run_time_utc.split(":", 1)]
        base = datetime.fromisoformat(date)
        return (base.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)).isoformat() + "Z"
    except Exception:
        return ""


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
