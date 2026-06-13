from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.command_center import CommandCenterEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.scheduler import ScheduledTask, SchedulerEngine, TaskKind, TaskResult, TaskStatus
from russworks.web import (
    BatterView,
    DashboardView,
    OperatorDashboardBuilder,
    PortfolioView,
    SchedulerView,
    SimulationView,
    SlipView,
    TeamView,
)

from tests.test_daily_pipeline import _slate


DATE = "2026-06-13"


def _task_handler(task: ScheduledTask, date: str) -> TaskResult:
    return TaskResult(
        task=task,
        status=TaskStatus.SUCCESS,
        started_at=f"{date}T00:00:00Z",
        finished_at=f"{date}T00:00:01Z",
        last_run=f"{date}T00:00:00Z",
        next_run=f"{date}T00:00:00Z",
        output_path="ok.json",
    )


def test_phase38_web_dashboard_models_are_dataclasses():
    assert is_dataclass(DashboardView)
    assert is_dataclass(BatterView)
    assert is_dataclass(TeamView)
    assert is_dataclass(SlipView)
    assert is_dataclass(PortfolioView)
    assert is_dataclass(SimulationView)
    assert is_dataclass(SchedulerView)


def test_operator_dashboard_builds_all_requested_views_and_exports_json():
    pipeline_result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(DATE, DailyRunRequest(date=DATE))
    scheduler = SchedulerEngine(task_handlers={TaskKind.PRE_SLATE_RUN: _task_handler}).run_schedule(
        DATE,
        tasks=[ScheduledTask("Pre-slate", TaskKind.PRE_SLATE_RUN, "10:00")],
    )
    command_center = CommandCenterEngine().build_report(daily_run_result=pipeline_result, scheduler_status=scheduler)
    dashboard = CalibrationDashboardEngine().build_dashboard(
        portfolio_profile=pipeline_result.portfolio_report,
        diversification_result=pipeline_result.diversification_report,
        simulation_result=pipeline_result.simulation_report,
        self_learning_report=pipeline_result.self_learning_report,
        scheduler_status=scheduler,
    )
    view = OperatorDashboardBuilder().build_dashboard(
        report=pipeline_result.full_report,
        dashboard=dashboard,
        command_center=command_center,
        scheduler_status=scheduler,
    )

    assert view.success
    assert view.metadata["report_date"] == DATE
    assert view.batters
    assert view.batters[0].russ_score >= view.batters[-1].russ_score
    assert view.teams
    assert view.slips
    assert view.portfolio.team_exposure
    assert view.portfolio.diversification_recommendations
    assert view.simulation.simulation_count == 1000
    assert view.scheduler.task_status_counts["success"] == 1
    assert "batter_confidence_grade_counts" in view.confidence_views
    assert view.explanations["batter_explanations"]
    assert view.command_center["formula_health"]["scheduler_summary"]["task_count"] == 1

    with TemporaryDirectory() as temp_dir:
        output_path = OperatorDashboardBuilder().export_json(view, temp_dir)
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path.name == "dashboard_data.json"
    assert payload["batters"]
    assert payload["scheduler"]["task_status_counts"]["success"] == 1


def test_operator_dashboard_builds_from_report_file_and_optional_sidecars():
    with TemporaryDirectory() as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        pipeline_result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline(
            DATE,
            DailyRunRequest(date=DATE, output_root=str(output_root)),
        )
        scheduler = SchedulerEngine(task_handlers={TaskKind.PRE_SLATE_RUN: _task_handler}).run_schedule(
            DATE,
            tasks=[ScheduledTask("Pre-slate", TaskKind.PRE_SLATE_RUN, "10:00")],
            output_dir=Path(temp_dir) / "scheduler",
        )
        command_center = CommandCenterEngine().build_report(daily_run_result=pipeline_result, scheduler_status=scheduler)
        command_path = Path(temp_dir) / "command_center.json"
        command_path.write_text(command_center.to_json(), encoding="utf-8")

        view = OperatorDashboardBuilder().build_from_report_file(
            pipeline_result.report_json_path,
            command_center_path=command_path,
            scheduler_path=Path(temp_dir) / "scheduler" / "scheduler_status.json",
        )

    assert view.metadata["validation_status"] == "valid"
    assert view.scheduler.tasks
    assert view.provider_health == []


def test_operator_dashboard_handles_empty_inputs_as_presentation_layer():
    view = OperatorDashboardBuilder().build_dashboard()

    assert view.success
    assert view.batters == []
    assert view.teams == []
    assert view.slips == []
    assert view.simulation.simulation_count == 0
