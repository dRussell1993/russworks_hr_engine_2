from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence

from russworks.cluster import ClusterRanking, generate_cluster_report
from russworks.data import CSVDataProvider, DailySlate, load_daily_slate
from russworks.postmortem import ActualHomeRunDataProvider, ActualHomeRunEntry, CSVHomeRunDataProvider
from russworks.postmortem import PostMortemEngine, PostMortemReport
from russworks.review import BatterReview, BatterReviewResult, review_all_batters
from russworks.slips import SlipPortfolio, generate_slip_portfolio

from .models import BacktestRequest, BacktestResult, BacktestSummary, DailyBacktestSummary


SlateLoader = Callable[[str], DailySlate]
ActualHomeRunLoader = Callable[[str], Iterable[ActualHomeRunEntry | dict[str, object]]]


@dataclass(frozen=True)
class _PipelineResult:
    step3_results: list[BatterReviewResult]
    cluster_ranking: ClusterRanking
    slip_portfolio: SlipPortfolio
    postmortem_report: PostMortemReport
    errors: list[str]


class HistoricalBacktestEngine:
    def __init__(
        self,
        *,
        slate_loader: SlateLoader | None = None,
        actual_hr_loader: ActualHomeRunLoader | None = None,
    ) -> None:
        self._slate_loader = slate_loader
        self._actual_hr_loader = actual_hr_loader

    def run(self, request: BacktestRequest) -> BacktestResult:
        daily_summaries: list[DailyBacktestSummary] = []
        recommendations = []
        errors: list[str] = []

        try:
            days = list(_date_range(request.start_date, request.end_date))
        except ValueError as exc:
            summary = _range_summary(request, [])
            return BacktestResult(request=request, daily_summaries=[], summary=summary, errors=[str(exc)])

        for day in days:
            day_text = day.isoformat()
            try:
                slate = self._load_slate(day_text, request)
                actual_home_runs = list(self._load_actual_home_runs(day_text, request))
                pipeline = self._run_daily_pipeline(slate, actual_home_runs)
                daily_summaries.append(_daily_summary(day_text, slate, actual_home_runs, pipeline))
                recommendations.extend(pipeline.postmortem_report.calibration_recommendations)
            except Exception as exc:  # Keep one bad historical date from stopping the full range.
                message = f"{day_text}: {exc}"
                errors.append(message)
                daily_summaries.append(
                    DailyBacktestSummary(
                        date=day_text,
                        games_reviewed=0,
                        total_batters_reviewed=0,
                        total_hrs_hit=0,
                        step3_hits=0,
                        step4_hits=0,
                        step5_hits=0,
                        non_superstar_hits=0,
                        ypi_hits=0,
                        veteran_hits=0,
                        catcher_hits=0,
                        weak_spot_hits=0,
                        pitch_mix_hits=0,
                        step3_hit_rate=0.0,
                        step4_hit_rate=0.0,
                        step5_hit_rate=0.0,
                        non_superstar_hit_rate=0.0,
                        ypi_hit_rate=0.0,
                        veteran_hit_rate=0.0,
                        catcher_hit_rate=0.0,
                        weak_spot_hit_rate=0.0,
                        pitch_mix_hit_rate=0.0,
                        errors=[message],
                    )
                )

        summary = _range_summary(request, daily_summaries)
        return BacktestResult(
            request=request,
            daily_summaries=daily_summaries,
            summary=summary,
            calibration_recommendations=_dedupe_recommendations(recommendations),
            errors=errors,
        )

    def export_json(self, result: BacktestResult, *, indent: int | None = 2) -> str:
        return result.to_json(indent=indent)

    def _load_slate(self, day: str, request: BacktestRequest) -> DailySlate:
        if self._slate_loader is not None:
            return self._slate_loader(day)
        provider = CSVDataProvider(Path(request.data_root) / day)
        return load_daily_slate(provider, day)

    def _load_actual_home_runs(
        self,
        day: str,
        request: BacktestRequest,
    ) -> Iterable[ActualHomeRunEntry | dict[str, object]]:
        if self._actual_hr_loader is not None:
            return self._actual_hr_loader(day)
        provider: ActualHomeRunDataProvider = CSVHomeRunDataProvider(Path(request.actual_hr_data_root) / f"actual_home_runs_raw_{day}.csv")
        return provider.fetch_home_runs(day)

    def _run_daily_pipeline(
        self,
        slate: DailySlate,
        actual_home_runs: Sequence[ActualHomeRunEntry | dict[str, object]],
    ) -> _PipelineResult:
        step3_results = [review_all_batters(game) for game in slate.games]
        combined_step3 = _combine_step3_results(step3_results)
        cluster_ranking = generate_cluster_report(combined_step3)
        slip_portfolio = generate_slip_portfolio(cluster_ranking)
        postmortem_report = PostMortemEngine().compare_to_step5_portfolio(slip_portfolio, actual_home_runs)
        errors = [
            *[error for result in step3_results for error in result.errors],
            *cluster_ranking.errors,
            *slip_portfolio.errors,
            *postmortem_report.errors,
        ]
        return _PipelineResult(
            step3_results=step3_results,
            cluster_ranking=cluster_ranking,
            slip_portfolio=slip_portfolio,
            postmortem_report=postmortem_report,
            errors=errors,
        )


def run_backtest(request: BacktestRequest) -> BacktestResult:
    return HistoricalBacktestEngine().run(request)


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


def _daily_summary(
    day: str,
    slate: DailySlate,
    actual_home_runs: Sequence[ActualHomeRunEntry | dict[str, object]],
    pipeline: _PipelineResult,
) -> DailyBacktestSummary:
    reviews = [review for result in pipeline.step3_results for review in result.reviews]
    actual_keys = {_actual_key(entry) for entry in actual_home_runs}
    step3_keys = {_review_key(review) for review in reviews}
    step4_team_keys = {report.team.lower() for report in pipeline.cluster_ranking.ranked_teams}
    step5_keys = {
        (leg.team.lower(), leg.batter.lower())
        for slip in pipeline.slip_portfolio.all_slips
        for leg in slip.legs
    }
    review_index = {_review_key(review): review for review in reviews}

    step3_hits = sum(1 for key in actual_keys if key in step3_keys)
    step4_hits = sum(1 for team, _ in actual_keys if team in step4_team_keys)
    step5_hits = sum(1 for key in actual_keys if key in step5_keys)
    matching_reviews = [review_index[key] for key in actual_keys if key in review_index]

    total_hrs = len(actual_home_runs)
    return DailyBacktestSummary(
        date=day,
        games_reviewed=slate.total_games,
        total_batters_reviewed=sum(result.reviewed_batters for result in pipeline.step3_results),
        total_hrs_hit=total_hrs,
        step3_hits=step3_hits,
        step4_hits=step4_hits,
        step5_hits=step5_hits,
        non_superstar_hits=sum(1 for review in matching_reviews if review.non_superstar_core_flag),
        ypi_hits=sum(1 for review in matching_reviews if review.ypi_flag),
        veteran_hits=sum(1 for review in matching_reviews if review.veteran_bounce_flag),
        catcher_hits=sum(1 for review in matching_reviews if review.catcher_power_flag),
        weak_spot_hits=sum(1 for review in matching_reviews if review.weak_spot_collision_flag),
        pitch_mix_hits=sum(1 for review in matching_reviews if review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"}),
        step3_hit_rate=_rate(step3_hits, total_hrs),
        step4_hit_rate=_rate(step4_hits, total_hrs),
        step5_hit_rate=_rate(step5_hits, total_hrs),
        non_superstar_hit_rate=_rate(sum(1 for review in matching_reviews if review.non_superstar_core_flag), total_hrs),
        ypi_hit_rate=_rate(sum(1 for review in matching_reviews if review.ypi_flag), total_hrs),
        veteran_hit_rate=_rate(sum(1 for review in matching_reviews if review.veteran_bounce_flag), total_hrs),
        catcher_hit_rate=_rate(sum(1 for review in matching_reviews if review.catcher_power_flag), total_hrs),
        weak_spot_hit_rate=_rate(sum(1 for review in matching_reviews if review.weak_spot_collision_flag), total_hrs),
        pitch_mix_hit_rate=_rate(
            sum(1 for review in matching_reviews if review.pitch_mix_matchup_grade in {"Elite", "Strong", "Moderate"}),
            total_hrs,
        ),
        errors=pipeline.errors,
    )


def _range_summary(request: BacktestRequest, daily_summaries: Sequence[DailyBacktestSummary]) -> BacktestSummary:
    totals = Counter()
    for daily in daily_summaries:
        totals["games"] += daily.games_reviewed
        totals["batters"] += daily.total_batters_reviewed
        totals["hrs"] += daily.total_hrs_hit
        totals["step3"] += daily.step3_hits
        totals["step4"] += daily.step4_hits
        totals["step5"] += daily.step5_hits
        totals["non_superstar"] += daily.non_superstar_hits
        totals["ypi"] += daily.ypi_hits
        totals["veteran"] += daily.veteran_hits
        totals["catcher"] += daily.catcher_hits
        totals["weak_spot"] += daily.weak_spot_hits
        totals["pitch_mix"] += daily.pitch_mix_hits

    total_hrs = totals["hrs"]
    return BacktestSummary(
        start_date=request.start_date,
        end_date=request.end_date,
        dates_tested=len(daily_summaries),
        total_games=totals["games"],
        total_batters_reviewed=totals["batters"],
        total_hrs_hit=total_hrs,
        step3_hits=totals["step3"],
        step4_hits=totals["step4"],
        step5_hits=totals["step5"],
        non_superstar_hits=totals["non_superstar"],
        ypi_hits=totals["ypi"],
        veteran_hits=totals["veteran"],
        catcher_hits=totals["catcher"],
        weak_spot_hits=totals["weak_spot"],
        pitch_mix_hits=totals["pitch_mix"],
        step3_hit_rate=_rate(totals["step3"], total_hrs),
        step4_hit_rate=_rate(totals["step4"], total_hrs),
        step5_hit_rate=_rate(totals["step5"], total_hrs),
        non_superstar_hit_rate=_rate(totals["non_superstar"], total_hrs),
        ypi_hit_rate=_rate(totals["ypi"], total_hrs),
        veteran_hit_rate=_rate(totals["veteran"], total_hrs),
        catcher_hit_rate=_rate(totals["catcher"], total_hrs),
        weak_spot_hit_rate=_rate(totals["weak_spot"], total_hrs),
        pitch_mix_hit_rate=_rate(totals["pitch_mix"], total_hrs),
    )


def _date_range(start_date: str, end_date: str) -> Iterable[date]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("Backtest end_date must be on or after start_date.")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _actual_key(entry: ActualHomeRunEntry | dict[str, object]) -> tuple[str, str]:
    if isinstance(entry, ActualHomeRunEntry):
        return (entry.team.lower(), entry.batter.lower())
    return (str(entry["team"]).lower(), str(entry["batter"]).lower())


def _review_key(review: BatterReview) -> tuple[str, str]:
    return (review.team.lower(), review.batter_name.lower())


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _dedupe_recommendations(recommendations):
    seen: set[tuple[str, str]] = set()
    deduped = []
    for recommendation in recommendations:
        key = (recommendation.module, recommendation.action)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(recommendation)
    return deduped
