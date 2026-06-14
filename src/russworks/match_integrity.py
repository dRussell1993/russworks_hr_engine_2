from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
import re
import unicodedata
from typing import Any, Mapping, Sequence

from russworks.postmortem import PostMortemReport


class ProductionReadinessStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass(frozen=True)
class PlaceholderPrediction:
    section: str
    batter: str
    team: str = ""
    reason: str = "Generated/sample/test batter name detected."


@dataclass(frozen=True)
class MatchIntegrityAudit:
    data_source_type: str = "unknown"
    production_readiness: str = ProductionReadinessStatus.WARNING.value
    placeholder_predictions_found: list[PlaceholderPrediction] = field(default_factory=list)
    real_prediction_records: int = 0
    predicted_batters_count: int = 0
    actual_hr_count: int = 0
    matched_actual_hr_count: int = 0
    unmatched_actual_hr_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    duplicate_prediction_count: int = 0
    duplicate_actual_hr_count: int = 0
    matched_predictions: int = 0
    total_predictions_evaluated: int = 0
    winning_legs: int = 0
    total_legs_evaluated: int = 0
    hit_rate: float = 0.0
    slip_hit_rate: float = 0.0
    hit_rate_formula_used: str = "matched_predictions / total_predictions_evaluated"
    slip_hit_rate_formula_used: str = "winning_legs / total_legs_evaluated"
    calibration_enabled: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def placeholder_prediction_count(self) -> int:
        return len(self.placeholder_predictions_found)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


_PLACEHOLDER_PATTERNS = [
    re.compile(r"^[A-Z]{2,3}\s+Batter\s+\d+$", re.IGNORECASE),
    re.compile(r"^Team\s+Batter\s+\d+$", re.IGNORECASE),
    re.compile(r"^(Sample|Test|Generated)\s+Batter(?:\s+\d+)?$", re.IGNORECASE),
    re.compile(r"^[A-Za-z .'-]+\s+Batter\s+\d+$", re.IGNORECASE),
]


def normalize_batter_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def is_placeholder_prediction_name(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return any(pattern.match(text) for pattern in _PLACEHOLDER_PATTERNS)


def build_match_integrity_audit(
    report_payload: Mapping[str, Any] | None,
    postmortem_report: PostMortemReport | None = None,
) -> MatchIntegrityAudit:
    payload = dict(report_payload or {})
    predicted_rows = _prediction_rows(payload)
    slip_legs = _slip_legs(payload)
    actual_entries = list(postmortem_report.actual_home_runs if postmortem_report else [])
    loser_count = len(postmortem_report.loser_log) if postmortem_report else 0
    false_positive_count = len(postmortem_report.false_positive_log) if postmortem_report else 0

    placeholders = _placeholder_predictions(payload, postmortem_report)
    prediction_names = [normalize_batter_name(row.get("batter")) for row in predicted_rows if normalize_batter_name(row.get("batter"))]
    actual_names = [normalize_batter_name(entry.batter) for entry in actual_entries if normalize_batter_name(entry.batter)]
    prediction_counts = Counter(prediction_names)
    actual_counts = Counter(actual_names)
    prediction_name_set = set(prediction_counts)

    matched_actual_hr_count = sum(1 for name in actual_names if name in prediction_name_set)
    matched_predictions = sum(1 for name in set(prediction_counts) if name in actual_counts)
    total_predictions_evaluated = len(predicted_rows)
    winning_legs = sum(
        1
        for leg in slip_legs
        if normalize_batter_name(leg.get("batter")) in actual_counts
    )
    total_legs_evaluated = len(slip_legs)
    unmatched_actual_hr_count = max(0, len(actual_names) - matched_actual_hr_count)
    duplicate_prediction_count = sum(count - 1 for count in prediction_counts.values() if count > 1)
    duplicate_actual_hr_count = sum(count - 1 for count in actual_counts.values() if count > 1)
    real_prediction_records = sum(1 for row in predicted_rows if not is_placeholder_prediction_name(row.get("batter")))
    warnings = []
    if placeholders:
        warnings.append("Placeholder prediction data detected; calibration disabled for this run.")
    if total_predictions_evaluated == 0:
        warnings.append("No prediction records were available for post-mortem match integrity.")
    if actual_entries and matched_actual_hr_count == 0:
        warnings.append("Actual HR records did not match any normalized prediction names.")
    if duplicate_prediction_count:
        warnings.append("Duplicate prediction batter names detected.")
    if duplicate_actual_hr_count:
        warnings.append("Duplicate actual HR batter names detected.")

    readiness = _readiness_status(
        placeholders=placeholders,
        total_predictions=total_predictions_evaluated,
        actual_count=len(actual_entries),
        matched_actual_hr_count=matched_actual_hr_count,
    )
    return MatchIntegrityAudit(
        data_source_type=_data_source_type(payload, placeholders),
        production_readiness=readiness.value,
        placeholder_predictions_found=placeholders,
        real_prediction_records=real_prediction_records,
        predicted_batters_count=len(prediction_counts),
        actual_hr_count=len(actual_entries),
        matched_actual_hr_count=matched_actual_hr_count,
        unmatched_actual_hr_count=unmatched_actual_hr_count,
        false_positive_count=false_positive_count or loser_count,
        false_negative_count=unmatched_actual_hr_count,
        duplicate_prediction_count=duplicate_prediction_count,
        duplicate_actual_hr_count=duplicate_actual_hr_count,
        matched_predictions=matched_predictions,
        total_predictions_evaluated=total_predictions_evaluated,
        winning_legs=winning_legs,
        total_legs_evaluated=total_legs_evaluated,
        hit_rate=_rate(matched_predictions, total_predictions_evaluated),
        slip_hit_rate=_rate(winning_legs, total_legs_evaluated),
        calibration_enabled=readiness != ProductionReadinessStatus.FAIL,
        warnings=warnings,
    )


def _readiness_status(
    *,
    placeholders: Sequence[PlaceholderPrediction],
    total_predictions: int,
    actual_count: int,
    matched_actual_hr_count: int,
) -> ProductionReadinessStatus:
    if placeholders:
        return ProductionReadinessStatus.FAIL
    if total_predictions <= 0:
        return ProductionReadinessStatus.FAIL
    if actual_count and matched_actual_hr_count == 0:
        return ProductionReadinessStatus.WARNING
    return ProductionReadinessStatus.PASS


def _prediction_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in _mapping(payload.get("step3")).get("batter_reviews", []) or [] if isinstance(row, Mapping)]


def _slip_legs(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    step5 = _mapping(payload.get("step5"))
    legs = []
    for key in ["core_slips", "non_superstar_core_slips", "balanced_slips", "chaos_slips", "contrarian_slips"]:
        for slip in step5.get(key, []) or []:
            if isinstance(slip, Mapping):
                legs.extend(leg for leg in slip.get("legs", []) or [] if isinstance(leg, Mapping))
    return legs


def _placeholder_predictions(
    payload: Mapping[str, Any],
    postmortem_report: PostMortemReport | None,
) -> list[PlaceholderPrediction]:
    found: list[PlaceholderPrediction] = []
    for row in _prediction_rows(payload):
        _append_placeholder(found, "step3", row.get("batter"), row.get("team"))
    for row in _mapping(payload.get("step4")).get("team_rankings", []) or []:
        if not isinstance(row, Mapping):
            continue
        team = row.get("team")
        for key in ["cluster_captain", "hidden_cluster_beneficiary"]:
            _append_placeholder(found, f"step4.{key}", row.get(key), team)
        for key in ["non_superstar_cluster_bats", "core_bats", "secondary_bats", "ypi_bats", "catcher_power_bats"]:
            for batter in row.get(key, []) or []:
                _append_placeholder(found, f"step4.{key}", batter, team)
    for leg in _slip_legs(payload):
        _append_placeholder(found, "step5.legs", leg.get("batter"), leg.get("team"))
    if postmortem_report:
        for entry in [*postmortem_report.loser_log, *postmortem_report.false_positive_log]:
            _append_placeholder(found, "postmortem.predictions", getattr(entry, "batter", ""), getattr(entry, "team", ""))
    return _dedupe_placeholders(found)


def _append_placeholder(found: list[PlaceholderPrediction], section: str, batter: Any, team: Any = "") -> None:
    if is_placeholder_prediction_name(batter):
        found.append(PlaceholderPrediction(section=section, batter=str(batter), team=str(team or "")))


def _dedupe_placeholders(values: Sequence[PlaceholderPrediction]) -> list[PlaceholderPrediction]:
    unique = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        key = (item.section, item.batter, item.team)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _data_source_type(payload: Mapping[str, Any], placeholders: Sequence[PlaceholderPrediction]) -> str:
    if placeholders:
        return "sample_or_generated_predictions"
    context = _mapping(payload.get("context"))
    validation = str(context.get("validation_status", "")).lower()
    if validation == "valid":
        return "real_prediction_output"
    return "unknown"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
