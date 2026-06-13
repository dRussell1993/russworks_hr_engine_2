from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .models import BatterScore, Game, PostMortemEntry, Slip, TeamClusterScore
from .scoring import calculate_team_clusters, score_game
from .validation import validate_step2

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.review import BatterReview, BatterReviewResult
from russworks.slips import Slip as Step5Slip
from russworks.slips import SlipPortfolio


REPORT_SCHEMA_VERSION = "1.0"
LEGACY_REPORT_SCHEMA_VERSION = "legacy"
SUPPORTED_REPORT_SCHEMA_VERSIONS = {REPORT_SCHEMA_VERSION, LEGACY_REPORT_SCHEMA_VERSION}


@dataclass(frozen=True)
class ReportContext:
    report_date: str
    games_reviewed: int
    validation_status: str
    game_ids: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    active_config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Step3Report:
    total_batters_reviewed: int
    batter_reviews: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Step4Report:
    team_rankings: List[Dict[str, Any]] = field(default_factory=list)
    cluster_rankings: List[Dict[str, Any]] = field(default_factory=list)
    non_superstar_core_rankings: List[Dict[str, Any]] = field(default_factory=list)
    ypi_rankings: List[Dict[str, Any]] = field(default_factory=list)
    veteran_bounce_rankings: List[Dict[str, Any]] = field(default_factory=list)
    catcher_power_rankings: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Step5Report:
    core_slips: List[Dict[str, Any]] = field(default_factory=list)
    non_superstar_core_slips: List[Dict[str, Any]] = field(default_factory=list)
    balanced_slips: List[Dict[str, Any]] = field(default_factory=list)
    chaos_slips: List[Dict[str, Any]] = field(default_factory=list)
    contrarian_slips: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class FullRussWorksReport:
    context: ReportContext
    step3: Step3Report
    step4: Step4Report
    step5: Step5Report
    schema_version: str = REPORT_SCHEMA_VERSION
    explanations: Dict[str, Any] = field(default_factory=dict)
    portfolio: Dict[str, Any] = field(default_factory=dict)
    diversification: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class ReportGenerator:
    def generate_step3_report(self, step3_results: BatterReviewResult | None) -> Step3Report:
        if step3_results is None:
            return Step3Report(total_batters_reviewed=0, errors=["Step 3 report requires Step 3 results."])

        reviews = sorted(step3_results.reviews, key=lambda review: (review.team, review.lineup_slot, review.batter_name))
        return Step3Report(
            total_batters_reviewed=step3_results.reviewed_batters,
            batter_reviews=[_batter_review_row(review) for review in reviews],
            errors=list(step3_results.errors),
        )

    def generate_step4_report(self, cluster_ranking: ClusterRanking | None) -> Step4Report:
        if cluster_ranking is None:
            return Step4Report(errors=["Step 4 report requires Step 4 cluster results."])

        ranked_teams = list(cluster_ranking.ranked_teams)
        return Step4Report(
            team_rankings=[_team_ranking_row(index, report) for index, report in enumerate(ranked_teams, start=1)],
            cluster_rankings=[_cluster_ranking_row(index, report) for index, report in enumerate(ranked_teams, start=1)],
            non_superstar_core_rankings=_special_batter_rankings(ranked_teams, "non_superstar"),
            ypi_rankings=_special_batter_rankings(ranked_teams, "ypi"),
            veteran_bounce_rankings=_special_batter_rankings(ranked_teams, "veteran_bounce"),
            catcher_power_rankings=_special_batter_rankings(ranked_teams, "catcher_power"),
            errors=list(cluster_ranking.errors),
        )

    def generate_step5_report(self, portfolio: SlipPortfolio | None) -> Step5Report:
        if portfolio is None:
            return Step5Report(errors=["Step 5 report requires Step 5 slip portfolio results."])

        return Step5Report(
            core_slips=[_slip_row(slip) for slip in portfolio.core_slips],
            non_superstar_core_slips=[_slip_row(slip) for slip in portfolio.non_superstar_core_slips],
            balanced_slips=[_slip_row(slip) for slip in portfolio.balanced_slips],
            chaos_slips=[_slip_row(slip) for slip in portfolio.chaos_slips],
            contrarian_slips=[_slip_row(slip) for slip in portfolio.contrarian_slips],
            errors=list(portfolio.errors),
        )

    def generate_full_report(
        self,
        *,
        context: ReportContext,
        step3_results: BatterReviewResult | None,
        cluster_ranking: ClusterRanking | None,
        slip_portfolio: SlipPortfolio | None,
        explanations: Mapping[str, Any] | None = None,
        portfolio: Mapping[str, Any] | None = None,
        diversification: Mapping[str, Any] | None = None,
    ) -> FullRussWorksReport:
        return FullRussWorksReport(
            context=context,
            step3=self.generate_step3_report(step3_results),
            step4=self.generate_step4_report(cluster_ranking),
            step5=self.generate_step5_report(slip_portfolio),
            explanations=dict(explanations or {}),
            portfolio=dict(portfolio or {}),
            diversification=dict(diversification or {}),
        )

    def export_json(self, report: FullRussWorksReport, *, indent: int | None = 2) -> str:
        return report.to_json(indent=indent)


def load_full_report_json(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return load_full_report_payload(json.load(handle))


def load_full_report_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Russ-Works report payload must be a JSON object.")

    schema_version = str(payload.get("schema_version", LEGACY_REPORT_SCHEMA_VERSION))
    if schema_version not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_REPORT_SCHEMA_VERSIONS))
        raise ValueError(f"Unsupported Russ-Works report schema_version {schema_version}; supported versions: {supported}.")

    normalized = dict(payload)
    normalized["schema_version"] = schema_version
    for section in ("context", "step3", "step4", "step5"):
        if not isinstance(normalized.get(section), Mapping):
            raise ValueError(f"Generated report missing {section} section.")
    return normalized


def _batter_review_row(review: BatterReview) -> Dict[str, Any]:
    return {
        "batter": review.batter_name,
        "team": review.team,
        "opponent": review.opponent,
        "lineup_slot": review.lineup_slot,
        "hr_pct": review.hr_pct,
        "russ_score": review.final_russ_score,
        "tier": _enum_value(review.russ_tier),
        "tag": review.tag_contribution,
        "cps": review.cps_contribution,
        "lstm": review.lstm_score,
        "pvs": review.pvs_contribution,
        "environment": review.environment_score,
        "umpire": review.umpire_score,
        "weak_spot_collision": {
            "flag": review.weak_spot_collision_flag,
            "score": review.weak_spot_collision_score,
            "confidence": review.weak_spot_collision_confidence,
            "grade": review.weak_spot_collision_grade,
        },
        "ypi": {
            "flag": review.ypi_flag,
            "score": review.ypi_score,
            "confidence": review.ypi_confidence,
            "grade": review.ypi_grade,
        },
        "veteran_bounce": {
            "flag": review.veteran_bounce_flag,
            "score": review.veteran_bounce_score,
            "confidence": review.veteran_bounce_confidence,
            "grade": review.veteran_bounce_grade,
        },
        "catcher_power": {
            "flag": review.catcher_power_flag,
            "score": review.catcher_power_score,
            "confidence": review.catcher_power_confidence,
            "grade": review.catcher_power_grade,
        },
        "pitch_mix": {
            "score": review.pitch_mix_matchup_score,
            "confidence": review.pitch_mix_matchup_confidence,
            "grade": review.pitch_mix_matchup_grade,
        },
        "bullpen": {
            "score": review.bullpen_exposure_score,
            "confidence": review.bullpen_exposure_confidence,
            "grade": review.bullpen_exposure_grade,
        },
        "park_factor": {
            "score": review.park_factor_score,
            "confidence": review.park_factor_confidence,
            "grade": review.park_factor_grade,
        },
        "confidence": {
            "score": review.confidence_score,
            "grade": review.confidence_grade,
            "reasoning": list(review.confidence_reasoning),
            "breakdown": dict(review.confidence_breakdown),
        },
        "non_superstar_core": review.non_superstar_core_flag,
        "notes": list(review.notes),
    }


def _team_ranking_row(rank: int, report: TeamClusterReport) -> Dict[str, Any]:
    return {
        "rank": rank,
        "team": report.team,
        "opponent": report.opponent,
        "tag_grade": report.tag_grade,
        "cps_grade": report.cps_grade,
        "total_cluster_score": report.total_cluster_score,
        "cluster_strength_label": report.cluster_strength_label,
        "cluster_captain": report.cluster_captain,
        "hidden_cluster_beneficiary": report.hidden_cluster_beneficiary,
        "batter_count": report.batter_count,
        "confidence": {
            "score": report.confidence_score,
            "grade": report.confidence_grade,
            "reasoning": list(report.confidence_reasoning),
            "breakdown": dict(report.confidence_breakdown),
        },
        "notes": list(report.notes),
    }


def _cluster_ranking_row(rank: int, report: TeamClusterReport) -> Dict[str, Any]:
    return {
        **_team_ranking_row(rank, report),
        "core_bats": list(report.core_bats),
        "secondary_bats": list(report.secondary_bats),
        "non_superstar_cluster_bats": list(report.non_superstar_cluster_bats),
        "ypi_bats": list(report.ypi_bats),
        "veteran_bounce_bats": list(report.veteran_bounce_bats),
        "catcher_power_bats": list(report.catcher_power_bats),
        "pitch_mix_matchup_bats": list(report.pitch_mix_matchup_bats),
        "bullpen_exposure_bats": list(report.bullpen_exposure_bats),
        "park_factor_bats": list(report.park_factor_bats),
    }


def _special_batter_rankings(reports: Sequence[TeamClusterReport], family: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for report in reports:
        batters = {
            "non_superstar": report.non_superstar_cluster_bats,
            "ypi": report.ypi_bats,
            "veteran_bounce": report.veteran_bounce_bats,
            "catcher_power": report.catcher_power_bats,
        }[family]
        for batter in batters:
            rows.append(
                {
                    "batter": batter,
                    "team": report.team,
                    "opponent": report.opponent,
                    "cluster_score": report.total_cluster_score,
                    "tag_grade": report.tag_grade,
                    "cps_grade": report.cps_grade,
                    "family": family,
                    "family_grade": _family_grade(report, family),
                    "cluster_strength_label": report.cluster_strength_label,
                }
            )
    rows.sort(key=lambda row: row["cluster_score"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def _family_grade(report: TeamClusterReport, family: str) -> str:
    if family == "ypi":
        return report.ypi_grade
    if family == "veteran_bounce":
        return report.veteran_bounce_grade
    if family == "catcher_power":
        return report.catcher_power_grade
    return report.cluster_strength_label


def _slip_row(slip: Step5Slip) -> Dict[str, Any]:
    return {
        "name": slip.name,
        "slip_type": slip.slip_type,
        "justification": slip.justification,
        "confidence": {
            "score": slip.confidence_score,
            "grade": slip.confidence_grade,
            "reasoning": list(slip.confidence_reasoning),
        },
        "metadata": dict(slip.metadata),
        "legs": [
            {
                "batter": leg.batter,
                "team": leg.team,
                "tag": leg.tag,
                "cps": leg.cps,
                "russ_score": leg.russ_score,
                "slip_role": leg.slip_role,
                "justification": leg.justification,
                "confidence": {
                    "score": leg.confidence_score,
                    "grade": leg.confidence_grade,
                    "reasoning": list(leg.confidence_reasoning),
                },
            }
            for leg in slip.legs
        ],
    }


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def step2_report(game: Game) -> str:
    env = game.environment
    rows = [
        ["Game", f"{env.away_team} @ {env.home_team}"],
        ["Park", env.park],
        ["Weather HR%", env.weather_hr_pct],
        ["Weather Feet", env.weather_distance_ft],
        ["Wind", f"{env.wind_mph} {env.wind_direction}"],
        ["Roof", env.roof],
        ["Umpire", env.umpire.name if env.umpire else ""],
        ["Away Pitcher", game.away_pitcher.name],
        ["Home Pitcher", game.home_pitcher.name],
    ]
    return "# STEP 2 — Game Confirmation\n\n" + md_table(["Field", "Value"], rows)


def step3_report(game: Game) -> str:
    validate_step2(game)
    clusters = calculate_team_clusters(game)
    scores = score_game(game)
    by_team: Dict[str, List[BatterScore]] = defaultdict(list)
    for s in scores:
        by_team[s.batter.team].append(s)

    lines = [f"# STEP 3 — FULL RUSS-WORKS REPORT", f"## Game: {game.environment.away_team} @ {game.environment.home_team}", "All batters reviewed. No shortcuts."]
    for team in [game.environment.away_team, game.environment.home_team]:
        opp = game.home_pitcher if team == game.environment.away_team else game.away_pitcher
        lines.append(f"\n## {team} vs {opp.name}\n")
        rows = []
        for s in sorted(by_team[team], key=lambda x: x.batter.lineup_slot):
            rows.append([
                s.batter.name,
                s.batter.lineup_slot,
                f"{s.batter.hr_pct:g}%",
                s.board,
                f"{s.lpas:g}",
                f"{s.pitcher_collision:g}",
                f"{s.final_score:g}",
                s.tier.value,
            ])
        lines.append(md_table(["Batter", "Slot", "HR%", "Board", "LPAS", "Collision", "Final", "Russ"], rows))
        c = clusters[team]
        lines.append(f"\n**{team} TAG:** {c.tag_grade} ({c.tag_score})  ")
        lines.append(f"**{team} CPS:** {c.cps_grade} ({c.cps_score})  ")
        lines.append(f"**Cluster Core:** {', '.join(c.core_batters)}")

    gold = sorted([s for s in scores if s.tier.value == "Gold"], key=lambda x: x.final_score, reverse=True)
    silver = sorted([s for s in scores if s.tier.value == "Silver"], key=lambda x: x.final_score, reverse=True)
    bronze = sorted([s for s in scores if s.tier.value == "Bronze"], key=lambda x: x.final_score, reverse=True)

    lines.append("\n# STEP 3 GOLD POOL\n")
    lines.append(md_table(["Rank", "Batter", "Team", "Score", "Why"], [[i+1, s.batter.name, s.batter.team, s.final_score, s.board] for i, s in enumerate(gold)]))
    lines.append("\n# SILVER POOL\n")
    lines.append(md_table(["Batter", "Team", "Score"], [[s.batter.name, s.batter.team, s.final_score] for s in silver]))
    lines.append("\n# BRONZE / CHAOS POOL\n")
    lines.append(md_table(["Batter", "Team", "Score"], [[s.batter.name, s.batter.team, s.final_score] for s in bronze]))
    return "\n".join(lines)


def step4_report(game: Game) -> str:
    validate_step2(game)
    clusters = calculate_team_clusters(game)
    rows = []
    for c in sorted(clusters.values(), key=lambda x: x.cluster_score, reverse=True):
        rows.append([c.team, c.tag_grade, c.tag_score, c.cps_grade, c.cps_score, c.cluster_score, ", ".join(c.core_batters)])
    return "# STEP 4 — TAG / CPS Cluster Construction\n\n" + md_table(["Team", "TAG", "TAG Score", "CPS", "CPS Score", "Cluster", "Core"], rows)


def step5_report(slips: List[Slip]) -> str:
    rows = [[s.name, s.slip_type, ", ".join(s.batters), s.grade, s.rationale] for s in slips]
    return "# STEP 5 — Slip Construction\n\n" + md_table(["Slip", "Type", "Batters", "Grade", "Why"], rows)


def postmortem_report(entries: List[PostMortemEntry]) -> str:
    winners = [e for e in entries if e.result.lower() == "winner"]
    losers = [e for e in entries if e.result.lower() == "loser"]
    false_pos = [e for e in entries if e.result.lower() == "false_positive"]
    lines = ["# POST-MORTEM REPORT", ""]
    lines.append("## Winners Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Pitch", "Pitcher", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.pitch or "", e.pitcher or "", e.notes] for e in winners]))
    lines.append("\n## Losers Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.notes] for e in losers]))
    lines.append("\n## False Positive Log")
    lines.append(md_table(["Date", "Batter", "Team", "Status", "Score", "Notes"], [[e.date, e.batter, e.team, e.formula_status, e.step3_score or "", e.notes] for e in false_pos]))
    return "\n".join(lines)
