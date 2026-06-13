from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from russworks.cluster import ClusterRanking, generate_cluster_report
from russworks.configuration import ConfigLoader, RussWorksUserConfig
from russworks.data import CSVDataProvider, DailySlate, load_daily_slate as load_slate_from_provider
from russworks.explainability import ExplainabilityEngine
from russworks.intake import ReviewQueue, validate_step2_intake
from russworks.reports import FullRussWorksReport, ReportGenerator
from russworks.review import BatterReviewResult, review_all_batters
from russworks.slips import SlipPortfolio, generate_slip_portfolio
from russworks.providers import (
    BallparkProvider,
    BaseballSavantProvider,
    DailySlateProvider,
    MLBStatsProvider,
    WeatherProvider,
)

from .models import DailyRunRequest, DailyRunResult


SlateLoader = Callable[[str, DailyRunRequest], DailySlate]


class RussWorksPipeline:
    def __init__(self, *, slate_loader: SlateLoader | None = None) -> None:
        self._slate_loader = slate_loader
        self._report_generator = ReportGenerator()
        self._active_config: RussWorksUserConfig | None = None

    def run_daily_pipeline(self, date: str, request: DailyRunRequest | None = None) -> DailyRunResult:
        run_request = request or DailyRunRequest(date=date)
        try:
            self._active_config = self.load_config(run_request)
            slate = self.load_daily_slate(run_request)
            validation_queues = self.validate_slate(slate)
            missing_data = _merge_missing_data(validation_queues)
            if missing_data:
                errors = _missing_data_errors(missing_data)
                return DailyRunResult(
                    request=run_request,
                    success=False,
                    validation_status="invalid",
                    missing_data=missing_data,
                    slate=slate,
                    errors=errors,
                )

            step3 = self.run_step3(slate)
            if not step3.success:
                return DailyRunResult(
                    request=run_request,
                    success=False,
                    validation_status="valid",
                    slate=slate,
                    step3_result=step3,
                    total_batters_reviewed=step3.reviewed_batters,
                    errors=list(step3.errors),
                )

            step4 = self.run_step4(step3)
            step5 = self.run_step5(step4)
            report = self.generate_full_report(slate, step3, step4, step5)
            output_dir, report_path = self.save_outputs(run_request, report)
            errors = [*step4.errors, *step5.errors]
            return DailyRunResult(
                request=run_request,
                success=not errors,
                validation_status="valid",
                total_batters_reviewed=step3.reviewed_batters,
                output_dir=str(output_dir),
                report_json_path=str(report_path),
                slate=slate,
                step3_result=step3,
                step4_result=step4,
                step5_result=step5,
                full_report=report,
                errors=errors,
            )
        except Exception as exc:
            return DailyRunResult(
                request=run_request,
                success=False,
                validation_status="error",
                errors=[str(exc)],
            )

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
            return slate_provider.load_daily_slate(request.date)
        return load_slate_from_provider(provider, request.date)

    def load_config(self, request: DailyRunRequest) -> RussWorksUserConfig:
        return ConfigLoader(request.config_path).load()

    def validate_slate(self, slate: DailySlate) -> list[ReviewQueue]:
        return [validate_step2_intake(game) for game in slate.games]

    def run_step3(self, slate: DailySlate) -> BatterReviewResult:
        results = [review_all_batters(game, user_config=self._active_config) for game in slate.games]
        return _combine_step3_results(results)

    def run_step4(self, step3_result: BatterReviewResult) -> ClusterRanking:
        return generate_cluster_report(step3_result, user_config=self._active_config)

    def run_step5(self, step4_result: ClusterRanking) -> SlipPortfolio:
        return generate_slip_portfolio(step4_result, user_config=self._active_config)

    def generate_full_report(
        self,
        slate: DailySlate,
        step3_result: BatterReviewResult,
        step4_result: ClusterRanking,
        step5_result: SlipPortfolio,
    ) -> FullRussWorksReport:
        context = slate.to_report_context()
        if self._active_config is not None:
            context = _context_with_config(context, self._active_config)
        explanations = ExplainabilityEngine().generate_explanations(
            step3_results=step3_result,
            cluster_ranking=step4_result,
            slip_portfolio=step5_result,
        )
        return self._report_generator.generate_full_report(
            context=context,
            step3_results=step3_result,
            cluster_ranking=step4_result,
            slip_portfolio=step5_result,
            explanations=explanations,
        )

    def save_outputs(self, request: DailyRunRequest, report: FullRussWorksReport) -> tuple[Path, Path]:
        output_dir = Path(request.output_root) / request.date
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "russworks_full_report.json"
        report_path.write_text(report.to_json(), encoding="utf-8")
        if report.explanations:
            ExplainabilityEngine().export_json(report.explanations, Path(request.output_root).parent / "explanations")
        return output_dir, report_path


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
        notes=[*context.notes, f"config_source={user_config.source_path}", f"risk_profile={user_config.risk_profile.profile}"],
        active_config=user_config.to_dict(),
    )
