from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from russworks.cluster import ClusterRanking, generate_cluster_report
from russworks.command_center import CommandCenterEngine, CommandCenterReport
from russworks.configuration import ConfigLoader, RussWorksUserConfig
from russworks.dashboard import CalibrationDashboard, CalibrationDashboardEngine
from russworks.data import CSVDataProvider, DailySlate, load_daily_slate as load_slate_from_provider
from russworks.diversification import DiversificationEngine, DiversificationResult
from russworks.explainability import ExplainabilityEngine
from russworks.integrity import IntegrityEngine, IntegrityReport
from russworks.intake import ReviewQueue, validate_step2_intake
from russworks.portfolio import PortfolioEngine, PortfolioProfile
from russworks.reports import FullRussWorksReport, ReportGenerator
from russworks.review import BatterReviewResult, review_all_batters
from russworks.self_learning import SelfLearningEngine, SelfLearningReport
from russworks.simulation import MonteCarloEngine, SimulationResult
from russworks.slips import SlipPortfolio, generate_slip_portfolio
from russworks.web import OperatorDashboardBuilder
from russworks.providers import (
    BallparkProvider,
    BaseballSavantProvider,
    DailySlateProvider,
    MLBStatsProvider,
    WeatherProvider,
)

from .models import DailyRunRequest, DailyRunResult
from .models import CompleteGame, IncompleteGame, SkippedGame


SlateLoader = Callable[[str, DailyRunRequest], DailySlate]
_SKIPPABLE_MISSING_CATEGORIES = {"weak_spot", "hr_matchup", "park_factor", "umpire"}


@dataclass(frozen=True)
class _GameValidationPlan:
    process_slate: DailySlate
    complete_games: list[CompleteGame]
    incomplete_games: list[IncompleteGame]
    skipped_games: list[SkippedGame]
    missing_data: dict[str, list[str]]
    validation_summary: dict[str, object]
    warnings: list[str]
    validation_status: str


class RussWorksPipeline:
    def __init__(self, *, slate_loader: SlateLoader | None = None) -> None:
        self._slate_loader = slate_loader
        self._report_generator = ReportGenerator()
        self._integrity_engine = IntegrityEngine()
        self._dashboard_engine = CalibrationDashboardEngine()
        self._command_center_engine = CommandCenterEngine()
        self._web_dashboard_builder = OperatorDashboardBuilder()
        self._portfolio_engine = PortfolioEngine()
        self._diversification_engine = DiversificationEngine()
        self._simulation_engine = MonteCarloEngine()
        self._self_learning_engine = SelfLearningEngine()
        self._active_config: RussWorksUserConfig | None = None
        self._provider_results = []
        self._provider_health = []

    def run_daily_pipeline(self, date: str, request: DailyRunRequest | None = None) -> DailyRunResult:
        run_request = request or DailyRunRequest(date=date)
        try:
            self._active_config = self.load_config(run_request)
            slate = self.load_daily_slate(run_request)
            validation_plan = self.validate_games(slate)
            integrity_source = validation_plan.process_slate if validation_plan.process_slate.games else slate
            integrity_report = self.run_integrity_checks(integrity_source)
            if not validation_plan.process_slate.games:
                errors = _missing_data_errors(validation_plan.missing_data)
                _, integrity_path = self.save_integrity_report(run_request, integrity_report)
                result = DailyRunResult(
                    request=run_request,
                    success=False,
                    validation_status="invalid",
                    missing_data=validation_plan.missing_data,
                    validation_summary=validation_plan.validation_summary,
                    complete_games=validation_plan.complete_games,
                    incomplete_games=validation_plan.incomplete_games,
                    skipped_games=validation_plan.skipped_games,
                    slate=slate,
                    integrity_report=integrity_report,
                    integrity_report_path=str(integrity_path),
                    warnings=validation_plan.warnings,
                    errors=errors,
                )
                return self.export_failure_runtime_outputs(run_request, result, integrity_report)

            step3 = self.run_step3(validation_plan.process_slate)
            if not step3.success:
                _, integrity_path = self.save_integrity_report(run_request, integrity_report)
                result = DailyRunResult(
                    request=run_request,
                    success=False,
                    validation_status=validation_plan.validation_status,
                    validation_summary=validation_plan.validation_summary,
                    complete_games=validation_plan.complete_games,
                    incomplete_games=validation_plan.incomplete_games,
                    skipped_games=validation_plan.skipped_games,
                    slate=validation_plan.process_slate,
                    integrity_report=integrity_report,
                    integrity_report_path=str(integrity_path),
                    step3_result=step3,
                    total_batters_reviewed=step3.reviewed_batters,
                    warnings=validation_plan.warnings,
                    errors=list(step3.errors),
                )
                return self.export_failure_runtime_outputs(run_request, result, integrity_report)

            step4 = self.run_step4(step3)
            step5 = self.run_step5(step4)
            portfolio = self.analyze_portfolio(step5)
            diversification = self.analyze_diversification(step5, portfolio)
            simulation = self.simulate_portfolio(step5, portfolio)
            self_learning = self.build_self_learning_report(simulation)
            report = self.generate_full_report(validation_plan.process_slate, step3, step4, step5, portfolio, diversification, simulation, self_learning, validation_plan)
            output_dir, report_path, operator_report_path = self.save_outputs(run_request, report)
            _, integrity_path = self.save_integrity_report(run_request, integrity_report)
            _, portfolio_path = self.save_portfolio_report(run_request, portfolio)
            _, diversification_path = self.save_diversification_report(run_request, diversification)
            _, simulation_path = self.save_simulation_report(run_request, simulation)
            _, self_learning_path = self.save_self_learning_report(run_request, self_learning)
            errors = [*step4.errors, *step5.errors]
            result = DailyRunResult(
                request=run_request,
                success=not errors,
                validation_status=validation_plan.validation_status,
                validation_summary=validation_plan.validation_summary,
                complete_games=validation_plan.complete_games,
                incomplete_games=validation_plan.incomplete_games,
                skipped_games=validation_plan.skipped_games,
                total_batters_reviewed=step3.reviewed_batters,
                output_dir=str(output_dir),
                report_json_path=str(report_path),
                operator_report_path=str(operator_report_path),
                integrity_report_path=str(integrity_path),
                portfolio_report_path=str(portfolio_path),
                diversification_report_path=str(diversification_path),
                simulation_report_path=str(simulation_path),
                self_learning_report_path=str(self_learning_path),
                slate=validation_plan.process_slate,
                integrity_report=integrity_report,
                portfolio_report=portfolio,
                diversification_report=diversification,
                simulation_report=simulation,
                self_learning_report=self_learning,
                step3_result=step3,
                step4_result=step4,
                step5_result=step5,
                full_report=report,
                warnings=validation_plan.warnings,
                errors=errors,
            )
            if errors:
                return self.export_failure_runtime_outputs(run_request, result, integrity_report)
            return self.export_success_runtime_outputs(run_request, result, integrity_report, portfolio, diversification, simulation, self_learning)
        except Exception as exc:
            result = DailyRunResult(
                request=run_request,
                success=False,
                validation_status="error",
                errors=[str(exc)],
            )
            return self.export_failure_runtime_outputs(run_request, result, None)

    def load_daily_slate(self, request: DailyRunRequest) -> DailySlate:
        if self._slate_loader is not None:
            return self._slate_loader(request.date, request)
        provider = CSVDataProvider(Path(request.data_root) / request.date)
        if request.provider_mode == "live":
            slate_provider = DailySlateProvider(
                providers=[
                    MLBStatsProvider(),
                    WeatherProvider(),
                    BallparkProvider(),
                    BaseballSavantProvider(),
                ],
                fallback_provider=provider,
            )
            slate = slate_provider.load_daily_slate(request.date)
            self._provider_results = list(slate_provider.results)
            self._provider_health = list(slate_provider.health_statuses)
            return slate
        self._provider_results = []
        self._provider_health = []
        return load_slate_from_provider(provider, request.date)

    def load_config(self, request: DailyRunRequest) -> RussWorksUserConfig:
        return ConfigLoader(request.config_path).load()

    def validate_slate(self, slate: DailySlate) -> list[ReviewQueue]:
        return [validate_step2_intake(game) for game in slate.games]

    def validate_games(self, slate: DailySlate) -> _GameValidationPlan:
        return _build_game_validation_plan(slate)

    def run_integrity_checks(self, slate: DailySlate) -> IntegrityReport:
        return self._integrity_engine.validate_daily_slate(
            slate,
            provider_results=self._provider_results,
            provider_health=self._provider_health,
        )

    def run_step3(self, slate: DailySlate) -> BatterReviewResult:
        results = [review_all_batters(game, user_config=self._active_config) for game in slate.games]
        return _combine_step3_results(results)

    def run_step4(self, step3_result: BatterReviewResult) -> ClusterRanking:
        return generate_cluster_report(step3_result, user_config=self._active_config)

    def run_step5(self, step4_result: ClusterRanking) -> SlipPortfolio:
        return generate_slip_portfolio(step4_result, user_config=self._active_config)

    def analyze_portfolio(self, step5_result: SlipPortfolio) -> PortfolioProfile:
        return self._portfolio_engine.analyze_portfolio(step5_result)

    def analyze_diversification(self, step5_result: SlipPortfolio, portfolio: PortfolioProfile) -> DiversificationResult:
        return self._diversification_engine.analyze_diversification(step5_result, portfolio_profile=portfolio)

    def simulate_portfolio(self, step5_result: SlipPortfolio, portfolio: PortfolioProfile) -> SimulationResult:
        return self._simulation_engine.simulate_portfolio(step5_result, portfolio_profile=portfolio)

    def build_self_learning_report(self, simulation: SimulationResult) -> SelfLearningReport:
        return self._self_learning_engine.build_report(simulation_result=simulation)

    def generate_full_report(
        self,
        slate: DailySlate,
        step3_result: BatterReviewResult,
        step4_result: ClusterRanking,
        step5_result: SlipPortfolio,
        portfolio: PortfolioProfile | None = None,
        diversification: DiversificationResult | None = None,
        simulation: SimulationResult | None = None,
        self_learning: SelfLearningReport | None = None,
        validation_plan: _GameValidationPlan | None = None,
    ) -> FullRussWorksReport:
        context = slate.to_report_context()
        if validation_plan is not None:
            context = _context_with_validation_plan(context, validation_plan)
        if self._active_config is not None:
            context = _context_with_config(context, self._active_config)
        explanations = ExplainabilityEngine().generate_explanations(
            step3_results=step3_result,
            cluster_ranking=step4_result,
            slip_portfolio=step5_result,
            portfolio_profile=portfolio,
            diversification_result=diversification,
            simulation_result=simulation,
            self_learning_report=self_learning,
        )
        return self._report_generator.generate_full_report(
            context=context,
            step3_results=step3_result,
            cluster_ranking=step4_result,
            slip_portfolio=step5_result,
            explanations=explanations,
            portfolio=portfolio.to_dict() if portfolio else {},
            diversification=diversification.to_dict() if diversification else {},
            simulation=simulation.to_dict() if simulation else {},
            self_learning=self_learning.to_dict() if self_learning else {},
        )

    def save_outputs(self, request: DailyRunRequest, report: FullRussWorksReport) -> tuple[Path, Path, Path]:
        output_dir = Path(request.output_root) / request.date
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "russworks_full_report.json"
        report_path.write_text(report.to_json(), encoding="utf-8")
        operator_report_path = output_dir / "russworks_operator_report.md"
        operator_report_path.write_text(self._report_generator.generate_operator_markdown(report), encoding="utf-8")
        if report.explanations:
            ExplainabilityEngine().export_json(report.explanations, Path(request.output_root).parent / "explanations")
        return output_dir, report_path, operator_report_path

    def save_integrity_report(self, request: DailyRunRequest, report: IntegrityReport) -> tuple[Path, Path]:
        integrity_dir = Path(request.output_root).parent / "integrity"
        return integrity_dir, self._integrity_engine.export_json(report, integrity_dir)

    def save_portfolio_report(self, request: DailyRunRequest, report: PortfolioProfile) -> tuple[Path, Path]:
        portfolio_dir = Path(request.output_root).parent / "portfolio"
        return portfolio_dir, self._portfolio_engine.export_json(report, portfolio_dir)

    def save_diversification_report(self, request: DailyRunRequest, report: DiversificationResult) -> tuple[Path, Path]:
        diversification_dir = Path(request.output_root).parent / "diversification"
        return diversification_dir, self._diversification_engine.export_json(report, diversification_dir)

    def save_simulation_report(self, request: DailyRunRequest, report: SimulationResult) -> tuple[Path, Path]:
        simulation_dir = Path(request.output_root).parent / "simulation"
        return simulation_dir, self._simulation_engine.export_json(report, simulation_dir)

    def save_self_learning_report(self, request: DailyRunRequest, report: SelfLearningReport) -> tuple[Path, Path]:
        self_learning_dir = Path(request.output_root).parent / "self_learning"
        return self_learning_dir, self._self_learning_engine.export_json(report, self_learning_dir)

    def export_success_runtime_outputs(
        self,
        request: DailyRunRequest,
        result: DailyRunResult,
        integrity_report: IntegrityReport,
        portfolio: PortfolioProfile,
        diversification: DiversificationResult,
        simulation: SimulationResult,
        self_learning: SelfLearningReport,
    ) -> DailyRunResult:
        dashboard = self._dashboard_engine.build_dashboard(
            integrity_report=integrity_report,
            portfolio_profile=portfolio,
            diversification_result=diversification,
            simulation_result=simulation,
            self_learning_report=self_learning,
            validation_summary=result.validation_summary,
            skipped_games=result.skipped_games,
        )
        dashboard_path = self.save_dashboard(request, dashboard)
        command_center = self._command_center_engine.build_report(
            date=request.date,
            daily_run_result=result,
            dashboard=dashboard,
            integrity_report=integrity_report,
            explanations_path=str(Path(request.output_root).parent / "explanations" / "explanations.json"),
        )
        command_center_path = self.save_command_center(request, command_center)
        web_dashboard_path = self.save_web_dashboard(request, result.full_report, dashboard, command_center)
        return _replace_result(
            result,
            dashboard_path=str(dashboard_path),
            command_center_path=str(command_center_path),
            web_dashboard_path=str(web_dashboard_path),
        )

    def export_failure_runtime_outputs(
        self,
        request: DailyRunRequest,
        result: DailyRunResult,
        integrity_report: IntegrityReport | None,
    ) -> DailyRunResult:
        command_center = self._command_center_engine.build_report(
            date=request.date,
            daily_run_result=result,
            integrity_report=integrity_report,
        )
        command_center_path = self.save_command_center(request, command_center)
        return _replace_result(
            result,
            command_center_path=str(command_center_path),
            errors=[*result.errors, *command_center.errors],
        )

    def save_dashboard(self, request: DailyRunRequest, dashboard: CalibrationDashboard) -> Path:
        dashboard_dir = Path(request.output_root).parent / "dashboard"
        return self._dashboard_engine.export_json(dashboard, dashboard_dir)

    def save_command_center(self, request: DailyRunRequest, command_center: CommandCenterReport) -> Path:
        command_center_dir = Path(request.output_root).parent / "command_center"
        return self._command_center_engine.export_json(command_center, command_center_dir)

    def save_web_dashboard(
        self,
        request: DailyRunRequest,
        report: FullRussWorksReport | None,
        dashboard: CalibrationDashboard,
        command_center: CommandCenterReport,
    ) -> Path:
        web_dir = Path(request.output_root).parent / "web"
        view = self._web_dashboard_builder.build_dashboard(
            report=report,
            dashboard=dashboard,
            command_center=command_center,
        )
        return self._web_dashboard_builder.export_json(view, web_dir)


def run_daily_pipeline(
    date: str,
    *,
    data_root: str = "data/daily",
    output_root: str = "data/outputs",
    provider_mode: str = "csv",
    config_path: str = "config/russworks_config.yaml",
) -> DailyRunResult:
    request = DailyRunRequest(date=date, data_root=data_root, output_root=output_root, provider_mode=provider_mode, config_path=config_path)
    return RussWorksPipeline().run_daily_pipeline(date, request)


def _combine_step3_results(results: Sequence[BatterReviewResult]) -> BatterReviewResult:
    reviews = [review for result in results for review in result.reviews]
    errors = [error for result in results for error in result.errors]
    skipped = [batter for result in results for batter in result.skipped_batters]
    return BatterReviewResult(
        total_batters=sum(result.total_batters for result in results),
        reviewed_batters=sum(result.reviewed_batters for result in results),
        reviews=reviews,
        errors=errors,
        skipped_batters=skipped,
    )


def _merge_missing_data(queues: Sequence[ReviewQueue]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for queue in queues:
        for category, values in queue.missing_data.items():
            merged.setdefault(category, [])
            for value in values:
                if value not in merged[category]:
                    merged[category].append(value)
    return {category: values for category, values in merged.items() if values}


def _build_game_validation_plan(slate: DailySlate) -> _GameValidationPlan:
    complete_games: list[CompleteGame] = []
    incomplete_games: list[IncompleteGame] = []
    skipped_games: list[SkippedGame] = []
    process_games = []
    all_missing: dict[str, list[str]] = {}

    for game in slate.games:
        queue = validate_step2_intake(game)
        missing = _with_required_optional_game_inputs(dict(queue.missing_data), game)
        if not missing:
            complete_games.append(_complete_game(game))
            process_games.append(game)
            continue

        _merge_missing_into(all_missing, missing)
        if any(category in _SKIPPABLE_MISSING_CATEGORIES for category in missing):
            skipped_games.append(_skipped_game(game, missing))
        else:
            incomplete_games.append(_incomplete_game(game, missing))

    validation_status = "valid"
    if skipped_games or incomplete_games:
        validation_status = "partial" if complete_games else "invalid"
    if not slate.games:
        validation_status = "no_games"

    process_slate = DailySlate(
        date=slate.date,
        games=process_games,
        watchlist=slate.watchlist,
        metadata={
            **slate.metadata,
            "validation_status": validation_status,
            "validation_summary": json.dumps(_validation_summary(slate, complete_games, incomplete_games, skipped_games), sort_keys=True),
        },
    )
    missing_data = all_missing if not complete_games else _non_skipped_missing_data(incomplete_games)
    missing_data = _with_unmatched_game_ids(missing_data, slate)
    summary = _validation_summary(slate, complete_games, incomplete_games, skipped_games)
    return _GameValidationPlan(
        process_slate=process_slate,
        complete_games=complete_games,
        incomplete_games=incomplete_games,
        skipped_games=skipped_games,
        missing_data=missing_data,
        validation_summary=summary,
        warnings=_skipped_game_warnings(skipped_games, incomplete_games),
        validation_status=validation_status,
    )


def _with_required_optional_game_inputs(missing: dict[str, list[str]], game) -> dict[str, list[str]]:
    updated = {category: list(values) for category, values in missing.items()}
    environment = game.environment
    if environment is None or getattr(environment, "park_hr_factor", 0.0) <= 0.0:
        updated.setdefault("park_factor", [])
        if "park factor data" not in updated["park_factor"]:
            updated["park_factor"].append("park factor data")
    return {category: values for category, values in updated.items() if values}


def _complete_game(game) -> CompleteGame:
    return CompleteGame(
        game_id=game.game_id,
        original_game_id=getattr(game, "original_game_id", "") or game.game_id,
        teams=[team.team for team in game.teams],
    )


def _incomplete_game(game, missing: dict[str, list[str]]) -> IncompleteGame:
    return IncompleteGame(
        game_id=game.game_id,
        original_game_id=getattr(game, "original_game_id", "") or game.game_id,
        teams=[team.team for team in game.teams],
        missing_data=missing,
    )


def _skipped_game(game, missing: dict[str, list[str]]) -> SkippedGame:
    return SkippedGame(
        game_id=game.game_id,
        original_game_id=getattr(game, "original_game_id", "") or game.game_id,
        teams=[team.team for team in game.teams],
        skipped_reason=_skip_reasons(missing),
        missing_data=missing,
    )


def _skip_reasons(missing: dict[str, list[str]]) -> list[str]:
    reasons = []
    for category in sorted(_SKIPPABLE_MISSING_CATEGORIES):
        for value in missing.get(category, []):
            reason = f"{category}: {value}"
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def _validation_summary(
    slate: DailySlate,
    complete_games: Sequence[CompleteGame],
    incomplete_games: Sequence[IncompleteGame],
    skipped_games: Sequence[SkippedGame],
) -> dict[str, object]:
    return {
        "total_games": slate.total_games,
        "complete_games": len(complete_games),
        "incomplete_games": len(incomplete_games),
        "skipped_games": len(skipped_games),
        "processed_game_ids": [game.game_id for game in complete_games],
        "skipped_game_ids": [game.game_id for game in skipped_games],
    }


def _skipped_game_warnings(skipped_games: Sequence[SkippedGame], incomplete_games: Sequence[IncompleteGame]) -> list[str]:
    warnings = []
    for game in skipped_games:
        warnings.append(f"Skipped {game.game_id}: {'; '.join(game.skipped_reason)}")
    for game in incomplete_games:
        warnings.append(f"Incomplete {game.game_id}: " + "; ".join(f"{category}: {', '.join(values)}" for category, values in sorted(game.missing_data.items())))
    return warnings


def _non_skipped_missing_data(incomplete_games: Sequence[IncompleteGame]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for game in incomplete_games:
        _merge_missing_into(merged, game.missing_data)
    return merged


def _merge_missing_into(target: dict[str, list[str]], missing: dict[str, list[str]]) -> None:
    for category, values in missing.items():
        target.setdefault(category, [])
        for value in values:
            if value not in target[category]:
                target[category].append(value)


def _skipped_games_payload(skipped_games: Sequence[SkippedGame]) -> list[dict[str, object]]:
    return [
        {
            "game_id": game.game_id,
            "original_game_id": game.original_game_id,
            "teams": list(game.teams),
            "skipped_reason": list(game.skipped_reason),
            "missing_data": {category: list(values) for category, values in game.missing_data.items()},
            "validation_status": game.validation_status,
        }
        for game in skipped_games
    ]


def _with_unmatched_game_ids(missing_data: dict[str, list[str]], slate: DailySlate) -> dict[str, list[str]]:
    raw = slate.metadata.get("unmatched_game_ids", "")
    if not raw:
        return missing_data
    try:
        unmatched = json.loads(raw)
    except json.JSONDecodeError:
        return missing_data
    if not isinstance(unmatched, dict):
        return missing_data
    merged = {category: list(values) for category, values in missing_data.items()}
    messages = merged.setdefault("unmatched_game_id", [])
    for dataset, values in sorted(unmatched.items()):
        if not isinstance(values, list):
            continue
        for value in values:
            message = f"{dataset}: {value}"
            if message not in messages:
                messages.append(message)
    if not messages:
        merged.pop("unmatched_game_id", None)
    return merged


def _missing_data_errors(missing_data: dict[str, list[str]]) -> list[str]:
    if not missing_data:
        return []
    parts = [f"{category}: {', '.join(values)}" for category, values in sorted(missing_data.items())]
    return ["Step 2 validation incomplete; daily pipeline blocked. " + "; ".join(parts)]


def _context_with_config(context, user_config: RussWorksUserConfig):
    return type(context)(
        report_date=context.report_date,
        games_reviewed=context.games_reviewed,
        validation_status=context.validation_status,
        game_ids=list(context.game_ids),
        skipped_games=list(context.skipped_games),
        validation_summary=dict(context.validation_summary),
        warnings=list(context.warnings),
        notes=[*context.notes, f"config_source={user_config.source_path}", f"risk_profile={user_config.risk_profile.profile}"],
        active_config=user_config.to_dict(),
    )


def _context_with_validation_plan(context, validation_plan: _GameValidationPlan):
    return type(context)(
        report_date=context.report_date,
        games_reviewed=len(validation_plan.complete_games),
        validation_status=validation_plan.validation_status,
        game_ids=[game.game_id for game in validation_plan.complete_games],
        skipped_games=_skipped_games_payload(validation_plan.skipped_games),
        validation_summary=dict(validation_plan.validation_summary),
        warnings=list(validation_plan.warnings),
        notes=[
            *context.notes,
            f"complete_games={len(validation_plan.complete_games)}",
            f"skipped_games={len(validation_plan.skipped_games)}",
            f"incomplete_games={len(validation_plan.incomplete_games)}",
        ],
        active_config=dict(context.active_config),
    )


def _replace_result(result: DailyRunResult, **changes) -> DailyRunResult:
    values = {
        "request": result.request,
        "success": result.success,
        "validation_status": result.validation_status,
        "missing_data": result.missing_data,
        "validation_summary": result.validation_summary,
        "complete_games": result.complete_games,
        "incomplete_games": result.incomplete_games,
        "skipped_games": result.skipped_games,
        "total_batters_reviewed": result.total_batters_reviewed,
        "output_dir": result.output_dir,
        "report_json_path": result.report_json_path,
        "operator_report_path": result.operator_report_path,
        "integrity_report_path": result.integrity_report_path,
        "portfolio_report_path": result.portfolio_report_path,
        "diversification_report_path": result.diversification_report_path,
        "simulation_report_path": result.simulation_report_path,
        "self_learning_report_path": result.self_learning_report_path,
        "dashboard_path": result.dashboard_path,
        "command_center_path": result.command_center_path,
        "web_dashboard_path": result.web_dashboard_path,
        "slate": result.slate,
        "integrity_report": result.integrity_report,
        "portfolio_report": result.portfolio_report,
        "diversification_report": result.diversification_report,
        "simulation_report": result.simulation_report,
        "self_learning_report": result.self_learning_report,
        "step3_result": result.step3_result,
        "step4_result": result.step4_result,
        "step5_result": result.step5_result,
        "full_report": result.full_report,
        "warnings": result.warnings,
        "errors": result.errors,
    }
    values.update(changes)
    return DailyRunResult(**values)
