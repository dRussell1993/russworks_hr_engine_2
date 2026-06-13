from __future__ import annotations

from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .models import ConfidenceBreakdown, ConfidenceProfile, ConfidenceResult


_WEIGHTS = {
    "data_completeness": 0.18,
    "sample_size_quality": 0.10,
    "lineup_confirmation": 0.12,
    "integrity_warnings": 0.14,
    "environment_certainty": 0.10,
    "pitch_mix_certainty": 0.10,
    "weak_spot_certainty": 0.10,
    "bullpen_certainty": 0.08,
    "historical_consistency": 0.08,
}


class ConfidenceEngine:
    def score_profile(self, profile: ConfidenceProfile) -> ConfidenceResult:
        values = profile.breakdown.to_dict()
        score = sum(_clamp(values[name]) * weight for name, weight in _WEIGHTS.items())
        rounded = round(score, 1)
        return ConfidenceResult(
            subject=profile.subject,
            subject_type=profile.subject_type,
            confidence_score=rounded,
            confidence_grade=self.grade_score(rounded),
            confidence_reasoning=_reasoning(profile.breakdown, profile.context),
            breakdown=profile.breakdown,
        )

    def grade_score(self, score: float) -> str:
        if score >= 90.0:
            return "Elite"
        if score >= 78.0:
            return "High"
        if score >= 62.0:
            return "Medium"
        if score >= 45.0:
            return "Low"
        return "Very Low"

    def score_review(
        self,
        *,
        subject: str,
        data_completeness: float,
        sample_size_quality: float,
        lineup_confirmation: float,
        integrity_warnings: float,
        environment_certainty: float,
        pitch_mix_certainty: float,
        weak_spot_certainty: float,
        bullpen_certainty: float,
        historical_consistency: float,
        context: Mapping[str, Any] | None = None,
    ) -> ConfidenceResult:
        return self.score_profile(
            ConfidenceProfile(
                subject=subject,
                subject_type="batter_review",
                breakdown=ConfidenceBreakdown(
                    data_completeness=data_completeness,
                    sample_size_quality=sample_size_quality,
                    lineup_confirmation=lineup_confirmation,
                    integrity_warnings=integrity_warnings,
                    environment_certainty=environment_certainty,
                    pitch_mix_certainty=pitch_mix_certainty,
                    weak_spot_certainty=weak_spot_certainty,
                    bullpen_certainty=bullpen_certainty,
                    historical_consistency=historical_consistency,
                ),
                context=dict(context or {}),
            )
        )

    def combine_results(
        self,
        subject: str,
        subject_type: str,
        results: Sequence[ConfidenceResult],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ConfidenceResult:
        if not results:
            return self.score_profile(
                ConfidenceProfile(
                    subject=subject,
                    subject_type=subject_type,
                    breakdown=ConfidenceBreakdown(),
                    context={"reason": "No confidence inputs were supplied.", **dict(context or {})},
                )
            )
        breakdown = ConfidenceBreakdown(
            data_completeness=_avg(result.breakdown.data_completeness for result in results),
            sample_size_quality=_avg(result.breakdown.sample_size_quality for result in results),
            lineup_confirmation=_avg(result.breakdown.lineup_confirmation for result in results),
            integrity_warnings=_avg(result.breakdown.integrity_warnings for result in results),
            environment_certainty=_avg(result.breakdown.environment_certainty for result in results),
            pitch_mix_certainty=_avg(result.breakdown.pitch_mix_certainty for result in results),
            weak_spot_certainty=_avg(result.breakdown.weak_spot_certainty for result in results),
            bullpen_certainty=_avg(result.breakdown.bullpen_certainty for result in results),
            historical_consistency=_avg(result.breakdown.historical_consistency for result in results),
        )
        return self.score_profile(ConfidenceProfile(subject=subject, subject_type=subject_type, breakdown=breakdown, context=dict(context or {})))

    def result_from_fields(
        self,
        *,
        subject: str,
        subject_type: str,
        confidence_score: float,
        confidence_grade: str,
        confidence_reasoning: Iterable[str] = (),
        breakdown: Mapping[str, Any] | ConfidenceBreakdown | None = None,
    ) -> ConfidenceResult:
        if isinstance(breakdown, ConfidenceBreakdown):
            confidence_breakdown = breakdown
        else:
            values = dict(breakdown or {})
            confidence_breakdown = ConfidenceBreakdown(**{field: float(values.get(field, 0.0)) for field in _WEIGHTS})
        return ConfidenceResult(
            subject=subject,
            subject_type=subject_type,
            confidence_score=round(_clamp(confidence_score), 1),
            confidence_grade=confidence_grade or self.grade_score(confidence_score),
            confidence_reasoning=list(confidence_reasoning),
            breakdown=confidence_breakdown,
        )

    def integrity_certainty(self, report: Any | None) -> float:
        if report is None:
            return 100.0
        counts = report.severity_counts
        penalty = counts.get("WARNING", 0) * 4.0 + counts.get("ERROR", 0) * 12.0 + counts.get("CRITICAL", 0) * 25.0
        return _clamp(100.0 - penalty)

    def summarize_results(self, results: Sequence[ConfidenceResult]) -> list[str]:
        if not results:
            return []
        avg_score = _avg(result.confidence_score for result in results)
        grades = sorted({result.confidence_grade for result in results})
        return [f"Confidence average {avg_score:.1f} across {len(results)} results; grades present: {', '.join(grades)}."]


def score_confidence(profile: ConfidenceProfile) -> ConfidenceResult:
    return ConfidenceEngine().score_profile(profile)


def _reasoning(breakdown: ConfidenceBreakdown, context: Mapping[str, Any]) -> list[str]:
    values = breakdown.to_dict()
    strongest = max(values, key=values.get)
    weakest = min(values, key=values.get)
    notes = [
        f"Strongest confidence input: {strongest.replace('_', ' ')} ({values[strongest]:.1f}).",
        f"Weakest confidence input: {weakest.replace('_', ' ')} ({values[weakest]:.1f}).",
    ]
    if context.get("reason"):
        notes.append(str(context["reason"]))
    if context.get("integrity_alerts"):
        notes.append(f"Integrity alerts considered: {context['integrity_alerts']}.")
    return notes


def _avg(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return round(mean(items), 1)


def _clamp(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, numeric))
