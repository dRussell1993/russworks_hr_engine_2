from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, List, Mapping, Sequence

from russworks.slips import Slip, SlipLeg, SlipPortfolio

from .models import (
    ActualHomeRunEntry,
    AdjustmentLogEntry,
    CalibrationRecommendation,
    FalsePositiveEntry,
    LoserLogEntry,
    PostMortemReport,
    WinnerLogEntry,
)

_REQUIRED_HR_FIELDS = {"team", "batter", "pitch", "pitcher", "inning", "exit_velocity", "distance", "angle"}


class PostMortemEngine:
    def __init__(self) -> None:
        self.actual_home_runs: List[ActualHomeRunEntry] = []
        self.winner_log: List[WinnerLogEntry] = []
        self.loser_log: List[LoserLogEntry] = []
        self.false_positive_log: List[FalsePositiveEntry] = []
        self.adjustment_log: List[AdjustmentLogEntry] = []
        self.calibration_recommendations: List[CalibrationRecommendation] = []
        self.errors: List[str] = []

    def ingest_actual_home_runs(self, actual_hr_entries: Iterable[Any]) -> List[ActualHomeRunEntry]:
        entries: List[ActualHomeRunEntry] = []
        for raw in actual_hr_entries:
            entry = _normalize_actual_hr_entry(raw)
            entries.append(entry)
        self.actual_home_runs.extend(entries)
        return entries

    def compare_to_step5_portfolio(
        self,
        portfolio: SlipPortfolio | None,
        actual_home_runs: Iterable[Any],
    ) -> PostMortemReport:
        errors = self._validate_portfolio(portfolio)
        actual_entries: List[ActualHomeRunEntry] = []
        try:
            actual_entries = self.ingest_actual_home_runs(actual_home_runs)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))

        if errors:
            self.errors.extend(errors)
            return self._report(errors=errors)

        assert portfolio is not None
        slip_index = _build_slip_index(portfolio)
        actual_keys = [_actual_key(entry) for entry in actual_entries]
        actual_key_set = set(actual_keys)

        new_winners = [self._winner_entry(entry, slip_index.get(_actual_key(entry), [])) for entry in actual_entries]
        new_losers = [
            self._loser_entry(slip, leg)
            for slip in portfolio.all_slips
            for leg in slip.legs
            if _leg_key(leg) not in actual_key_set
        ]
        new_false_positives = [entry for entry in (self._false_positive_entry(loser) for loser in new_losers) if entry]
        new_adjustments = self._build_adjustment_entries(new_winners, new_losers, new_false_positives)
        new_recommendations = self._build_calibration_recommendations(new_adjustments)

        self.winner_log.extend(new_winners)
        self.loser_log.extend(new_losers)
        self.false_positive_log.extend(new_false_positives)
        self.adjustment_log.extend(new_adjustments)
        self.calibration_recommendations.extend(new_recommendations)
        return self._report()

    def generate_winner_log(self) -> List[WinnerLogEntry]:
        return list(self.winner_log)

    def generate_loser_log(self) -> List[LoserLogEntry]:
        return list(self.loser_log)

    def generate_false_positive_log(self) -> List[FalsePositiveEntry]:
        return list(self.false_positive_log)

    def generate_adjustment_log(self) -> List[AdjustmentLogEntry]:
        return list(self.adjustment_log)

    def generate_calibration_recommendations(self) -> List[CalibrationRecommendation]:
        return list(self.calibration_recommendations)

    def build_dashboard(self, calibration_result=None, backtest_result=None):
        from russworks.dashboard import CalibrationDashboardEngine

        return CalibrationDashboardEngine().build_dashboard(
            calibration_result=calibration_result,
            postmortem_reports=[self._report()],
            backtest_result=backtest_result,
        )

    def _validate_portfolio(self, portfolio: SlipPortfolio | None) -> List[str]:
        if portfolio is None:
            return ["Post-mortem requires a Step 5 slip portfolio."]
        if not portfolio.success:
            return ["Post-mortem blocked because Step 5 portfolio contains errors.", *portfolio.errors]
        if not portfolio.all_slips:
            return ["Post-mortem requires at least one Step 5 slip."]
        return []

    def _winner_entry(self, actual: ActualHomeRunEntry, hits: Sequence[tuple[Slip, SlipLeg]]) -> WinnerLogEntry:
        archetypes = sorted({archetype for slip, leg in hits for archetype in _archetypes_for_leg(slip, leg)})
        if not archetypes:
            archetypes = ["Missed By Step 5"]
        return WinnerLogEntry(
            team=actual.team,
            batter=actual.batter,
            pitch=actual.pitch,
            pitcher=actual.pitcher,
            inning=actual.inning,
            exit_velocity=actual.exit_velocity,
            distance=actual.distance,
            angle=actual.angle,
            slip_names=sorted({slip.name for slip, _ in hits}),
            slip_types=sorted({slip.slip_type for slip, _ in hits}),
            archetypes=archetypes,
            source="step5_hit" if hits else "missed_by_step5",
        )

    def _loser_entry(self, slip: Slip, leg: SlipLeg) -> LoserLogEntry:
        archetypes = _archetypes_for_leg(slip, leg)
        return LoserLogEntry(
            team=leg.team,
            batter=leg.batter,
            slip_name=slip.name,
            slip_type=slip.slip_type,
            tag=leg.tag,
            cps=leg.cps,
            russ_score=leg.russ_score,
            slip_role=leg.slip_role,
            archetypes=archetypes,
            reason=_loser_reason(leg, archetypes),
        )

    def _false_positive_entry(self, loser: LoserLogEntry) -> FalsePositiveEntry | None:
        high_confidence = loser.russ_score >= 90.0 or (loser.tag in {"A", "A+"} and loser.cps in {"A", "A+"})
        if not high_confidence:
            return None
        modules = _modules_for_archetypes(loser.archetypes, loser.tag, loser.cps)
        return FalsePositiveEntry(
            team=loser.team,
            batter=loser.batter,
            slip_name=loser.slip_name,
            slip_type=loser.slip_type,
            reason="High-confidence Step 5 leg missed the actual HR list.",
            overweighted_modules=modules,
            suggested_adjustment="Review overweighted modules after sample-size threshold; do not auto-change weights.",
        )

    def _build_adjustment_entries(
        self,
        winners: Sequence[WinnerLogEntry],
        losers: Sequence[LoserLogEntry],
        false_positives: Sequence[FalsePositiveEntry],
    ) -> List[AdjustmentLogEntry]:
        entries: List[AdjustmentLogEntry] = []
        winner_counts = Counter(archetype for winner in winners for archetype in winner.archetypes)
        loser_counts = Counter(archetype for loser in losers for archetype in loser.archetypes)
        false_positive_modules = Counter(module for entry in false_positives for module in entry.overweighted_modules)

        for archetype, count in sorted(winner_counts.items()):
            if count >= 2 and archetype != "Missed By Step 5":
                entries.append(
                    AdjustmentLogEntry(
                        module=archetype,
                        direction="monitor_or_slightly_increase",
                        reason="Recurring winner archetype appeared in Step 5 hits.",
                        evidence_count=count,
                        recommendation="Track hit rate over more slates before increasing weights.",
                    )
                )
        for archetype, count in sorted(loser_counts.items()):
            if count >= 2 and count > winner_counts.get(archetype, 0):
                entries.append(
                    AdjustmentLogEntry(
                        module=archetype,
                        direction="review_or_slightly_reduce",
                        reason="Loser archetype appeared more often than winner archetype.",
                        evidence_count=count,
                        recommendation="Review thresholds; no automatic formula change.",
                    )
                )
        for module, count in sorted(false_positive_modules.items()):
            entries.append(
                AdjustmentLogEntry(
                    module=module,
                    direction="review_false_positive_pressure",
                    reason="Module contributed to high-confidence misses.",
                    evidence_count=count,
                    recommendation="Audit component weight before any manual calibration.",
                )
            )
        return entries

    def _build_calibration_recommendations(
        self,
        adjustments: Sequence[AdjustmentLogEntry],
    ) -> List[CalibrationRecommendation]:
        recommendations: List[CalibrationRecommendation] = []
        seen: set[tuple[str, str]] = set()
        for adjustment in adjustments:
            key = (adjustment.module, adjustment.direction)
            if key in seen:
                continue
            seen.add(key)
            recommendations.append(
                CalibrationRecommendation(
                    module=adjustment.module,
                    action=adjustment.direction,
                    suggested_delta=_suggested_delta(adjustment.direction, adjustment.evidence_count),
                    confidence=_confidence(adjustment.evidence_count),
                    rationale=f"{adjustment.reason} {adjustment.recommendation}",
                    supporting_archetypes=[adjustment.module],
                )
            )
        return recommendations

    def _report(self, errors: Sequence[str] = ()) -> PostMortemReport:
        return PostMortemReport(
            actual_home_runs=list(self.actual_home_runs),
            winner_log=self.generate_winner_log(),
            loser_log=self.generate_loser_log(),
            false_positive_log=self.generate_false_positive_log(),
            adjustment_log=self.generate_adjustment_log(),
            calibration_recommendations=self.generate_calibration_recommendations(),
            errors=list(errors),
        )


_DEFAULT_ENGINE = PostMortemEngine()


def ingest_actual_home_runs(actual_hr_entries: Iterable[Any]) -> List[ActualHomeRunEntry]:
    return _DEFAULT_ENGINE.ingest_actual_home_runs(actual_hr_entries)


def compare_to_step5_portfolio(portfolio: SlipPortfolio | None, actual_home_runs: Iterable[Any]) -> PostMortemReport:
    return PostMortemEngine().compare_to_step5_portfolio(portfolio, actual_home_runs)


def generate_winner_log(engine: PostMortemEngine | None = None) -> List[WinnerLogEntry]:
    return (engine or _DEFAULT_ENGINE).generate_winner_log()


def generate_loser_log(engine: PostMortemEngine | None = None) -> List[LoserLogEntry]:
    return (engine or _DEFAULT_ENGINE).generate_loser_log()


def generate_false_positive_log(engine: PostMortemEngine | None = None) -> List[FalsePositiveEntry]:
    return (engine or _DEFAULT_ENGINE).generate_false_positive_log()


def generate_adjustment_log(engine: PostMortemEngine | None = None) -> List[AdjustmentLogEntry]:
    return (engine or _DEFAULT_ENGINE).generate_adjustment_log()


def generate_calibration_recommendations(engine: PostMortemEngine | None = None) -> List[CalibrationRecommendation]:
    return (engine or _DEFAULT_ENGINE).generate_calibration_recommendations()


def _normalize_actual_hr_entry(raw: Any) -> ActualHomeRunEntry:
    if isinstance(raw, ActualHomeRunEntry):
        return raw
    data = asdict(raw) if is_dataclass(raw) else dict(raw) if isinstance(raw, Mapping) else None
    if data is None:
        raise TypeError("Actual HR entries must be mappings, dataclasses, or ActualHomeRunEntry instances.")
    missing = sorted(_REQUIRED_HR_FIELDS - set(data))
    if missing:
        raise KeyError(f"Actual HR entry missing required fields: {', '.join(missing)}")
    return ActualHomeRunEntry(
        team=str(data["team"]),
        batter=str(data["batter"]),
        pitch=str(data["pitch"]),
        pitcher=str(data["pitcher"]),
        inning=int(data["inning"]),
        exit_velocity=float(data["exit_velocity"]),
        distance=float(data["distance"]),
        angle=float(data["angle"]),
        metadata={str(key): str(value) for key, value in dict(data.get("metadata", {})).items()},
    )


def _build_slip_index(portfolio: SlipPortfolio) -> dict[tuple[str, str], List[tuple[Slip, SlipLeg]]]:
    index: dict[tuple[str, str], List[tuple[Slip, SlipLeg]]] = defaultdict(list)
    for slip in portfolio.all_slips:
        for leg in slip.legs:
            index[_leg_key(leg)].append((slip, leg))
    return dict(index)


def _actual_key(entry: ActualHomeRunEntry) -> tuple[str, str]:
    return (entry.team.lower(), entry.batter.lower())


def _leg_key(leg: SlipLeg) -> tuple[str, str]:
    return (leg.team.lower(), leg.batter.lower())


def _archetypes_for_leg(slip: Slip, leg: SlipLeg) -> List[str]:
    metadata_text = " ".join(str(value) for value in slip.metadata.values())
    haystack = " ".join([
        slip.name,
        slip.slip_type,
        slip.justification,
        metadata_text,
        leg.batter,
        leg.slip_role,
        leg.justification,
    ]).lower()
    archetypes: List[str] = []
    if "non-superstar" in haystack or "non_superstar" in haystack or "hidden" in haystack or "value" in haystack:
        archetypes.append("Non-Superstar")
    if "ypi" in haystack or "young" in haystack:
        archetypes.append("YPI")
    if "veteran" in haystack or "bounce" in haystack or "rebound" in haystack:
        archetypes.append("Veteran Bounce")
    if "catcher" in haystack:
        archetypes.append("Catcher Power")
    if "pitch mix" in haystack or "pitch_mix" in haystack or "pitch-type" in haystack or "pitch type" in haystack:
        archetypes.append("Pitch Mix Matchup")
    if "bullpen exposure" in haystack or "bullpen_exposure" in haystack or "bullpen" in haystack:
        archetypes.append("Bullpen Exposure")
    if "park factor" in haystack or "park_factor" in haystack or "park path" in haystack:
        archetypes.append("Park Factor")
    if "chaos" in haystack or "higher-variance" in haystack:
        archetypes.append("Chaos")
    if "contrarian" in haystack or "overlooked" in haystack or "secondary" in haystack:
        archetypes.append("Almost Made It")
    if "core" in haystack:
        archetypes.append("Core")
    if "balanced" in haystack:
        archetypes.append("Balanced")
    return _unique(archetypes)


def _loser_reason(leg: SlipLeg, archetypes: Sequence[str]) -> str:
    if "Chaos" in archetypes:
        return "Higher-variance chaos leg missed actual HR list."
    if "Catcher Power" in archetypes:
        return "Catcher Power leg missed actual HR list."
    if "Veteran Bounce" in archetypes:
        return "Veteran Bounce rebound leg missed actual HR list."
    if "Pitch Mix Matchup" in archetypes:
        return "Pitch Mix Matchup leg missed actual HR list."
    if "Bullpen Exposure" in archetypes:
        return "Bullpen Exposure leg missed actual HR list."
    if "Park Factor" in archetypes:
        return "Park Factor leg missed actual HR list."
    if "Non-Superstar" in archetypes:
        return "Value-backed non-superstar leg missed actual HR list."
    if leg.tag in {"A", "A+"} and leg.cps in {"A", "A+"}:
        return "Elite TAG/CPS leg missed actual HR list."
    return "Step 5 leg did not hit actual HR list."


def _modules_for_archetypes(archetypes: Sequence[str], tag: str, cps: str) -> List[str]:
    modules = list(archetypes)
    if tag in {"A", "A+"}:
        modules.append("TAG")
    if cps in {"A", "A+"}:
        modules.append("CPS")
    return _unique(modules or ["Step 5"])


def _suggested_delta(direction: str, evidence_count: int) -> float:
    if "increase" in direction:
        return min(0.05, evidence_count * 0.01)
    if "reduce" in direction or "false_positive" in direction:
        return -min(0.05, evidence_count * 0.01)
    return 0.0


def _confidence(evidence_count: int) -> str:
    if evidence_count >= 6:
        return "medium"
    return "low"


def _unique(values: Iterable[str]) -> List[str]:
    unique: List[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique
