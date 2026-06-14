from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from russworks.calibration import FormulaCalibrationEngine
from russworks.dashboard import CalibrationDashboardEngine
from russworks.models import RussTier
from russworks.optimizer import FormulaOptimizer
from russworks.postmortem import (
    CSVHomeRunDataProvider,
    MLBStatsHomeRunDataProvider,
    PostMortemEngine,
    PostMortemIngestionRunner,
    PostMortemNotReady,
    normalize_actual_home_run_entry,
)
from russworks.recommendations import WeightRecommendationEngine
from russworks.reports import load_full_report_json
from russworks.review import BatterReview, BatterReviewResult
from russworks.slips import Slip, SlipLeg, SlipPortfolio
from russworks.trends import TrendEngine

from .models import DailyPostMortemRun, PostMortemRunResult


class AutoPostMortemRunner:
    def run_postmortem(self, date: str, run: DailyPostMortemRun | None = None) -> PostMortemRunResult:
        request = run or DailyPostMortemRun(date=date)
        actual_path = _actual_hr_path(request)
        report_path = _report_path(request)
        date_dir = Path(request.postmortem_output_dir) / request.date
        metadata_path = date_dir / "run_metadata.json"

        if not actual_path.exists():
            try:
                actual_path = _acquire_actual_home_runs(request)
            except PostMortemNotReady:
                return PostMortemRunResult(
                    run=request,
                    success=True,
                    skipped=True,
                    messages=["Postmortem not ready."],
                )
            except Exception as exc:
                return PostMortemRunResult(
                    run=request,
                    success=True,
                    skipped=True,
                    messages=[f"Actual HR file missing and automatic acquisition failed for {request.date}: {exc}"],
                )

        if metadata_path.exists() and not request.force:
            return PostMortemRunResult(
                run=request,
                success=True,
                skipped=True,
                duplicate=True,
                metadata_path=str(metadata_path),
                messages=[f"Post-mortem already processed for {request.date}; use force=True to rerun."],
            )

        if not report_path.exists():
            return PostMortemRunResult(
                run=request,
                success=False,
                errors=[f"Generated Russ-Works report missing for {request.date}: {report_path}"],
            )

        try:
            actual_entries = _load_actual_home_runs(actual_path, request.date)
            report_payload = load_full_report_json(report_path)
            portfolio = _portfolio_from_report(report_payload)
            step3_result = _step3_from_report(report_payload)
            postmortem_report = PostMortemEngine().compare_to_step5_portfolio(portfolio, actual_entries)
            calibration_result = FormulaCalibrationEngine().calibrate_reviews(
                step3_result,
                postmortem_report.actual_home_runs,
                postmortem_reports=[postmortem_report],
            )
            dashboard = CalibrationDashboardEngine().build_dashboard(
                calibration_result=calibration_result,
                postmortem_reports=[postmortem_report],
                report_payload=report_payload,
            )
            recommendations = WeightRecommendationEngine().build_recommendations(
                calibration_result=calibration_result,
                dashboard=dashboard,
            )
            trends = TrendEngine().build_trends(
                dashboard=dashboard,
                calibration_result=calibration_result,
                recommendation_report=recommendations,
            )
            optimizer = FormulaOptimizer().optimize(
                calibration_result=calibration_result,
                dashboard=dashboard,
                recommendation_report=recommendations,
                trend_summary=trends,
            )
        except Exception as exc:
            return PostMortemRunResult(run=request, success=False, errors=[str(exc)])

        date_dir.mkdir(parents=True, exist_ok=True)
        dashboard_dir = Path(request.dashboard_output_dir)
        recommendations_dir = Path(request.recommendations_output_dir)
        trends_dir = Path(request.trends_output_dir)
        optimizer_dir = Path(request.optimizer_output_dir)
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        recommendations_dir.mkdir(parents=True, exist_ok=True)
        trends_dir.mkdir(parents=True, exist_ok=True)
        optimizer_dir.mkdir(parents=True, exist_ok=True)

        postmortem_path = date_dir / "postmortem_report.json"
        calibration_path = date_dir / "calibration_result.json"
        dashboard_path = CalibrationDashboardEngine().export_json(dashboard, dashboard_dir)
        recommendations_path = WeightRecommendationEngine().export_json(recommendations, recommendations_dir)
        trends_path = TrendEngine().export_json(trends, trends_dir)
        optimizer_path = FormulaOptimizer().export_json(optimizer, optimizer_dir)

        _write_json(postmortem_path, postmortem_report)
        calibration_path.write_text(calibration_result.to_json(), encoding="utf-8")

        result = PostMortemRunResult(
            run=request,
            success=(
                postmortem_report.success
                and calibration_result.success
                and dashboard.success
                and recommendations.success
                and trends.success
                and optimizer.success
            ),
            skipped=False,
            actual_home_runs_loaded=len(actual_entries),
            postmortem_report_path=str(postmortem_path),
            calibration_report_path=str(calibration_path),
            dashboard_path=str(dashboard_path),
            recommendations_path=str(recommendations_path),
            trends_path=str(trends_path),
            optimizer_path=str(optimizer_path),
            metadata_path=str(metadata_path),
            postmortem_report=postmortem_report,
            calibration_result=calibration_result,
            dashboard=dashboard,
            recommendations=recommendations,
            trends=trends,
            optimizer=optimizer,
            messages=[f"Auto post-mortem completed for {request.date}."],
            errors=[
                *postmortem_report.errors,
                *calibration_result.errors,
                *dashboard.errors,
                *recommendations.errors,
                *trends.errors,
                *optimizer.errors,
            ],
        )
        _write_metadata(metadata_path, result, actual_path, report_path)
        return result


def run_postmortem(date: str, run: DailyPostMortemRun | None = None) -> PostMortemRunResult:
    return AutoPostMortemRunner().run_postmortem(date, run)


def _actual_hr_path(request: DailyPostMortemRun) -> Path:
    if request.actual_hr_path:
        return Path(request.actual_hr_path)
    return Path(request.postmortem_output_dir) / f"actual_home_runs_{request.date}.csv"


def _acquire_actual_home_runs(request: DailyPostMortemRun) -> Path:
    runner = PostMortemIngestionRunner(
        provider=MLBStatsHomeRunDataProvider(),
        output_dir=request.postmortem_output_dir,
    )
    runner.run(request.date)
    return Path(request.postmortem_output_dir) / f"actual_home_runs_{request.date}.csv"


def _report_path(request: DailyPostMortemRun) -> Path:
    if request.report_path:
        return Path(request.report_path)
    return Path("data/outputs") / request.date / "russworks_full_report.json"


def _load_actual_home_runs(path: Path, date: str):
    rows = CSVHomeRunDataProvider(path).fetch_home_runs(date)
    return [normalize_actual_home_run_entry(row, date=date) for row in rows]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _portfolio_from_report(payload: Mapping[str, Any]) -> SlipPortfolio:
    step5 = payload.get("step5")
    if not isinstance(step5, Mapping):
        raise ValueError("Generated report missing step5 section.")
    return SlipPortfolio(
        core_slips=_slips(step5.get("core_slips", [])),
        non_superstar_core_slips=_slips(step5.get("non_superstar_core_slips", [])),
        balanced_slips=_slips(step5.get("balanced_slips", [])),
        chaos_slips=_slips(step5.get("chaos_slips", [])),
        contrarian_slips=_slips(step5.get("contrarian_slips", [])),
        errors=[str(error) for error in step5.get("errors", [])],
    )


def _slips(rows: Any) -> list[Slip]:
    slips = []
    for row in rows or []:
        slips.append(
            Slip(
                name=str(row.get("name", "")),
                slip_type=str(row.get("slip_type", "")),
                legs=[
                    SlipLeg(
                        batter=str(leg.get("batter", "")),
                        team=str(leg.get("team", "")),
                        tag=str(leg.get("tag", "")),
                        cps=str(leg.get("cps", "")),
                        russ_score=float(leg.get("russ_score", 0.0)),
                        slip_role=str(leg.get("slip_role", "")),
                        justification=str(leg.get("justification", "")),
                    )
                    for leg in row.get("legs", [])
                ],
                justification=str(row.get("justification", "")),
                metadata={str(key): str(value) for key, value in dict(row.get("metadata", {})).items()},
            )
        )
    return slips


def _step3_from_report(payload: Mapping[str, Any]) -> BatterReviewResult:
    step3 = payload.get("step3")
    if not isinstance(step3, Mapping):
        raise ValueError("Generated report missing step3 section.")
    reviews = [_review(row) for row in step3.get("batter_reviews", [])]
    total = int(step3.get("total_batters_reviewed", len(reviews)) or len(reviews))
    return BatterReviewResult(
        total_batters=total,
        reviewed_batters=len(reviews),
        reviews=reviews,
        errors=[str(error) for error in step3.get("errors", [])],
    )


def _review(row: Mapping[str, Any]) -> BatterReview:
    weak_spot = _mapping(row.get("weak_spot_collision"))
    ypi = _mapping(row.get("ypi"))
    veteran = _mapping(row.get("veteran_bounce"))
    catcher = _mapping(row.get("catcher_power"))
    pitch_mix = _mapping(row.get("pitch_mix"))
    bullpen = _mapping(row.get("bullpen"))
    park_factor = _mapping(row.get("park_factor"))
    return BatterReview(
        batter_name=str(row.get("batter", "")),
        team=str(row.get("team", "")),
        opponent=str(row.get("opponent", "")),
        lineup_slot=int(row.get("lineup_slot", 0) or 0),
        hr_pct=float(row.get("hr_pct", 0.0) or 0.0),
        lstm_score=float(row.get("lstm", 0.0) or 0.0),
        tag_contribution=float(row.get("tag", 0.0) or 0.0),
        cps_contribution=float(row.get("cps", 0.0) or 0.0),
        pvs_contribution=float(row.get("pvs", 0.0) or 0.0),
        environment_score=float(row.get("environment", 0.0) or 0.0),
        umpire_score=float(row.get("umpire", 0.0) or 0.0),
        ypi_flag=bool(ypi.get("flag", False)),
        catcher_power_flag=bool(catcher.get("flag", False)),
        veteran_bounce_flag=bool(veteran.get("flag", False)),
        non_superstar_core_flag=bool(row.get("non_superstar_core", False)),
        weak_spot_collision_flag=bool(weak_spot.get("flag", False)),
        final_russ_score=float(row.get("russ_score", 0.0) or 0.0),
        russ_tier=_tier(row.get("tier", "No")),
        notes=[str(note) for note in row.get("notes", [])],
        weak_spot_collision_score=float(weak_spot.get("score", 0.0) or 0.0),
        weak_spot_collision_confidence=float(weak_spot.get("confidence", 0.0) or 0.0),
        weak_spot_collision_grade=str(weak_spot.get("grade", "D")),
        ypi_score=float(ypi.get("score", 0.0) or 0.0),
        ypi_confidence=float(ypi.get("confidence", 0.0) or 0.0),
        ypi_grade=str(ypi.get("grade", "Weak")),
        veteran_bounce_score=float(veteran.get("score", 0.0) or 0.0),
        veteran_bounce_confidence=float(veteran.get("confidence", 0.0) or 0.0),
        veteran_bounce_grade=str(veteran.get("grade", "Weak")),
        catcher_power_score=float(catcher.get("score", 0.0) or 0.0),
        catcher_power_confidence=float(catcher.get("confidence", 0.0) or 0.0),
        catcher_power_grade=str(catcher.get("grade", "Weak")),
        pitch_mix_matchup_score=float(pitch_mix.get("score", 0.0) or 0.0),
        pitch_mix_matchup_confidence=float(pitch_mix.get("confidence", 0.0) or 0.0),
        pitch_mix_matchup_grade=str(pitch_mix.get("grade", "Weak")),
        bullpen_exposure_score=float(bullpen.get("score", 0.0) or 0.0),
        bullpen_exposure_confidence=float(bullpen.get("confidence", 0.0) or 0.0),
        bullpen_exposure_grade=str(bullpen.get("grade", "Weak")),
        park_factor_score=float(park_factor.get("score", 0.0) or 0.0),
        park_factor_confidence=float(park_factor.get("confidence", 0.0) or 0.0),
        park_factor_grade=str(park_factor.get("grade", "Neutral")),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _tier(value: Any) -> RussTier:
    text = str(value)
    for tier in RussTier:
        if tier.value == text:
            return tier
    return RussTier.NO


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_json_ready(value), indent=2, sort_keys=True), encoding="utf-8")


def _write_metadata(metadata_path: Path, result: PostMortemRunResult, actual_path: Path, report_path: Path) -> None:
    metadata = {
        "date": result.run.date,
        "status": "success" if result.success else "failed",
        "executed_at": _now(),
        "actual_hr_path": str(actual_path),
        "report_path": str(report_path),
        "actual_home_runs_loaded": result.actual_home_runs_loaded,
        "postmortem_report_path": result.postmortem_report_path,
        "calibration_report_path": result.calibration_report_path,
        "dashboard_path": result.dashboard_path,
        "recommendations_path": result.recommendations_path,
        "trends_path": result.trends_path,
        "optimizer_path": result.optimizer_path,
        "messages": list(result.messages),
        "errors": list(result.errors),
    }
    _write_json(metadata_path, metadata)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
