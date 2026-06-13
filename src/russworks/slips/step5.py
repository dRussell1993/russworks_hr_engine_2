from __future__ import annotations

from typing import Iterable, List, Sequence

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.configuration import RussWorksUserConfig, default_user_config

from .models import Slip, SlipLeg, SlipPortfolio


class Step5SlipEngine:
    def __init__(self, user_config: RussWorksUserConfig | None = None) -> None:
        self.user_config = (user_config or default_user_config()).validate()

    def generate_slip_portfolio(self, cluster_report: ClusterRanking | None) -> SlipPortfolio:
        errors = self._validate_cluster_report(cluster_report)
        if errors:
            return SlipPortfolio(errors=errors)

        assert cluster_report is not None
        prefs = self.user_config.slip_preferences
        portfolio = SlipPortfolio(
            core_slips=self.generate_core_slips(cluster_report) if prefs.allow_core_slips else [],
            non_superstar_core_slips=self.generate_non_superstar_core_slips(cluster_report) if prefs.allow_non_superstar_core else [],
            balanced_slips=self.generate_balanced_slips(cluster_report) if prefs.allow_balanced_slips else [],
            chaos_slips=self.generate_chaos_slips(cluster_report) if prefs.allow_chaos_slips else [],
            contrarian_slips=self.generate_contrarian_slips(cluster_report) if prefs.allow_contrarian_slips else [],
        )
        return self._limit_portfolio(self._dedupe_and_validate(portfolio))

    def generate_core_slips(self, cluster_report: ClusterRanking) -> List[Slip]:
        slips: List[Slip] = []
        for team_report in _ranked_reports(cluster_report)[:2]:
            candidates = _unique_names([team_report.cluster_captain, *team_report.core_bats, team_report.hidden_cluster_beneficiary])
            legs = [
                _leg(team_report, batter, "core", f"Core slip leg from strongest TAG/CPS cluster with {team_report.ypi_grade} YPI, {team_report.veteran_bounce_grade} Veteran Bounce, {team_report.catcher_power_grade} Catcher Power, {team_report.pitch_mix_matchup_grade} Pitch Mix, {team_report.bullpen_exposure_grade} Bullpen Exposure, and {team_report.park_factor_grade} Park Factor context.")
                for batter in candidates[:3]
            ]
            slip = _slip(
                name=f"{team_report.team} Core Cluster",
                slip_type="core",
                legs=self._limit_legs(legs),
                justification=f"Built around the strongest TAG/CPS cluster while keeping formula fit ahead of name value. YPI grade: {team_report.ypi_grade}. Veteran Bounce grade: {team_report.veteran_bounce_grade}. Catcher Power grade: {team_report.catcher_power_grade}. Pitch Mix grade: {team_report.pitch_mix_matchup_grade}. Bullpen Exposure grade: {team_report.bullpen_exposure_grade}. Park Factor grade: {team_report.park_factor_grade}.",
                cluster=team_report,
            )
            if slip:
                slips.append(slip)
        return slips

    def generate_non_superstar_core_slips(self, cluster_report: ClusterRanking) -> List[Slip]:
        slips: List[Slip] = []
        for team_report in _ranked_reports(cluster_report):
            value_pool = _unique_names([
                team_report.hidden_cluster_beneficiary,
                *team_report.non_superstar_cluster_bats,
                *team_report.ypi_bats,
                *team_report.veteran_bounce_bats,
                *team_report.catcher_power_bats,
                *team_report.pitch_mix_matchup_bats,
                *team_report.bullpen_exposure_bats,
                *team_report.park_factor_bats,
            ])
            candidates = [name for name in value_pool if name != team_report.cluster_captain]
            if len(candidates) < 2:
                candidates = value_pool
            legs = [
                _leg(team_report, batter, "non-superstar core", f"Value-oriented leg backed by Step 4 non-superstar, hidden-beneficiary, YPI, Veteran Bounce, Catcher Power, Pitch Mix, Bullpen Exposure, or Park Factor context. Park Factor grade: {team_report.park_factor_grade}.")
                for batter in candidates[:3]
            ]
            slip = _slip(
                name=f"{team_report.team} Non-Superstar Core",
                slip_type="non_superstar_core",
                legs=self._limit_legs(legs),
                justification=f"Prioritizes hidden cluster beneficiaries, value bats, and Step 4 non-superstar core flags. YPI grade: {team_report.ypi_grade}. Veteran Bounce grade: {team_report.veteran_bounce_grade}. Catcher Power grade: {team_report.catcher_power_grade}. Pitch Mix grade: {team_report.pitch_mix_matchup_grade}. Bullpen Exposure grade: {team_report.bullpen_exposure_grade}. Park Factor grade: {team_report.park_factor_grade}.",
                cluster=team_report,
                min_legs=2,
            )
            if slip:
                slips.append(slip)
        return slips

    def generate_balanced_slips(self, cluster_report: ClusterRanking) -> List[Slip]:
        reports = _ranked_reports(cluster_report)
        if not reports:
            return []

        slips: List[Slip] = []
        top = reports[0]
        candidates = _unique_names([
            top.cluster_captain,
            top.hidden_cluster_beneficiary,
            *(top.core_bats[:2]),
            *(top.non_superstar_cluster_bats[:2]),
            *(top.veteran_bounce_bats[:1]),
            *(top.catcher_power_bats[:1]),
            *(top.pitch_mix_matchup_bats[:1]),
            *(top.bullpen_exposure_bats[:1]),
            *(top.park_factor_bats[:1]),
        ])
        legs = [
            _leg(top, batter, "balanced", f"Balanced leg combining elite cluster strength, value support, YPI, Veteran Bounce, Catcher Power, Pitch Mix, Bullpen Exposure, and {top.park_factor_grade} Park Factor context.")
            for batter in candidates[:3]
        ]
        slip = _slip(
            name=f"{top.team} Balanced Formula",
            slip_type="balanced",
            legs=self._limit_legs(legs),
            justification=f"Mixes elite cluster bats and value bats from the highest-ranked cluster. YPI grade: {top.ypi_grade}. Veteran Bounce grade: {top.veteran_bounce_grade}. Catcher Power grade: {top.catcher_power_grade}. Pitch Mix grade: {top.pitch_mix_matchup_grade}. Bullpen Exposure grade: {top.bullpen_exposure_grade}. Park Factor grade: {top.park_factor_grade}.",
            cluster=top,
        )
        if slip:
            slips.append(slip)

        if len(reports) > 1:
            second = reports[1]
            cross_candidates = _unique_names([
                top.cluster_captain,
                top.hidden_cluster_beneficiary,
                second.cluster_captain,
                second.hidden_cluster_beneficiary,
            ])
            legs = []
            for batter in cross_candidates[:4]:
                source = top if batter in _all_report_names(top) else second
                legs.append(_leg(source, batter, "balanced", f"Cross-cluster balance leg preserving TAG/CPS context, YPI pressure, Veteran Bounce, Catcher Power, Pitch Mix, Bullpen Exposure, and {source.park_factor_grade} Park Factor context."))
            slip = _slip(
                name="Cross-Cluster Balanced Formula",
                slip_type="balanced",
                legs=self._limit_legs(legs),
                justification=f"Balances the top-ranked cluster with an overlooked bat from the next viable cluster. Top YPI grade: {top.ypi_grade}. Top Veteran Bounce grade: {top.veteran_bounce_grade}. Top Catcher Power grade: {top.catcher_power_grade}. Top Pitch Mix grade: {top.pitch_mix_matchup_grade}. Top Bullpen Exposure grade: {top.bullpen_exposure_grade}. Top Park Factor grade: {top.park_factor_grade}.",
                cluster=top,
                min_legs=3,
            )
            if slip:
                slips.append(slip)
        return slips

    def generate_chaos_slips(self, cluster_report: ClusterRanking) -> List[Slip]:
        slips: List[Slip] = []
        for team_report in _ranked_reports(cluster_report):
            candidates = _unique_names([
                *team_report.ypi_bats,
                *team_report.veteran_bounce_bats,
                *team_report.catcher_power_bats,
                *team_report.pitch_mix_matchup_bats,
                *team_report.bullpen_exposure_bats,
                *team_report.park_factor_bats,
                *team_report.secondary_bats,
                team_report.hidden_cluster_beneficiary,
            ])
            legs = [
                _leg(team_report, batter, "chaos", f"Higher-variance leg allowed through catcher, YPI, Veteran Bounce, Pitch Mix, Bullpen Exposure, Park Factor, or cluster-extension logic. Park Factor grade: {team_report.park_factor_grade}.")
                for batter in candidates[:3]
            ]
            slip = _slip(
                name=f"{team_report.team} Chaos Cluster",
                slip_type="chaos",
                legs=self._limit_legs(legs),
                justification=f"Higher-variance construction that allows catcher power, YPI, veteran bounce, Pitch Mix, Bullpen Exposure, Park Factor, and cluster-extension profiles. YPI grade: {team_report.ypi_grade}. Veteran Bounce grade: {team_report.veteran_bounce_grade}. Catcher Power grade: {team_report.catcher_power_grade}. Pitch Mix grade: {team_report.pitch_mix_matchup_grade}. Bullpen Exposure grade: {team_report.bullpen_exposure_grade}. Park Factor grade: {team_report.park_factor_grade}.",
                cluster=team_report,
                min_legs=2,
            )
            if slip:
                slips.append(slip)
        return slips

    def generate_contrarian_slips(self, cluster_report: ClusterRanking) -> List[Slip]:
        slips: List[Slip] = []
        reports = list(reversed(_ranked_reports(cluster_report)))
        for team_report in reports[:2]:
            candidates = _unique_names([
                team_report.hidden_cluster_beneficiary,
                *team_report.secondary_bats,
                *team_report.non_superstar_cluster_bats,
                *team_report.ypi_bats,
                *team_report.veteran_bounce_bats,
                *team_report.catcher_power_bats,
                *team_report.pitch_mix_matchup_bats,
                *team_report.bullpen_exposure_bats,
                *team_report.park_factor_bats,
            ])
            legs = [
                _leg(team_report, batter, "contrarian", f"Lower-ownership style leg from an overlooked or secondary cluster path with YPI, Veteran Bounce, Catcher Power, Pitch Mix, Bullpen Exposure, and {team_report.park_factor_grade} Park Factor context.")
                for batter in candidates[:3]
            ]
            slip = _slip(
                name=f"{team_report.team} Contrarian Cluster",
                slip_type="contrarian",
                legs=self._limit_legs(legs),
                justification=f"Lower-ownership style construction that leverages overlooked cluster paths. YPI grade: {team_report.ypi_grade}. Veteran Bounce grade: {team_report.veteran_bounce_grade}. Catcher Power grade: {team_report.catcher_power_grade}. Pitch Mix grade: {team_report.pitch_mix_matchup_grade}. Bullpen Exposure grade: {team_report.bullpen_exposure_grade}. Park Factor grade: {team_report.park_factor_grade}.",
                cluster=team_report,
                min_legs=2,
            )
            if slip:
                slips.append(slip)
        return slips

    def _validate_cluster_report(self, cluster_report: ClusterRanking | None) -> List[str]:
        if cluster_report is None:
            return ["Step 5 requires Step 4 cluster results."]
        errors: List[str] = []
        if not cluster_report.success:
            errors.append("Step 5 blocked because Step 4 results contain errors.")
            errors.extend(cluster_report.errors)
        if not cluster_report.ranked_teams:
            errors.append("Step 5 requires at least one ranked Step 4 team cluster.")
        return errors

    def _limit_legs(self, legs: Sequence[SlipLeg]) -> List[SlipLeg]:
        return list(legs)[: self.user_config.slip_preferences.legs_per_slip]

    def _limit_portfolio(self, portfolio: SlipPortfolio) -> SlipPortfolio:
        max_slips = self.user_config.slip_preferences.max_slips
        if max_slips >= len(portfolio.all_slips):
            return portfolio
        remaining = max_slips
        groups = []
        for slips in [
            portfolio.core_slips,
            portfolio.non_superstar_core_slips,
            portfolio.balanced_slips,
            portfolio.chaos_slips,
            portfolio.contrarian_slips,
        ]:
            keep = list(slips)[: max(0, remaining)]
            remaining -= len(keep)
            groups.append(keep)
        return SlipPortfolio(
            core_slips=groups[0],
            non_superstar_core_slips=groups[1],
            balanced_slips=groups[2],
            chaos_slips=groups[3],
            contrarian_slips=groups[4],
            errors=list(portfolio.errors),
        )

    def _dedupe_and_validate(self, portfolio: SlipPortfolio) -> SlipPortfolio:
        seen: set[tuple[str, ...]] = set()
        errors: List[str] = []
        core = self._dedupe_slips(portfolio.core_slips, seen, errors)
        non_superstar = self._dedupe_slips(portfolio.non_superstar_core_slips, seen, errors)
        balanced = self._dedupe_slips(portfolio.balanced_slips, seen, errors)
        chaos = self._dedupe_slips(portfolio.chaos_slips, seen, errors)
        contrarian = self._dedupe_slips(portfolio.contrarian_slips, seen, errors)
        return SlipPortfolio(
            core_slips=core,
            non_superstar_core_slips=non_superstar,
            balanced_slips=balanced,
            chaos_slips=chaos,
            contrarian_slips=contrarian,
            errors=errors,
        )

    def _dedupe_slips(self, slips: Sequence[Slip], seen: set[tuple[str, ...]], errors: List[str]) -> List[Slip]:
        deduped: List[Slip] = []
        for slip in slips:
            batter_key = tuple(sorted(leg.batter for leg in slip.legs))
            if len(batter_key) != len(set(batter_key)):
                errors.append(f"Duplicate batter found in slip: {slip.name}")
                continue
            if batter_key in seen:
                continue
            if not slip.justification or any(not leg.justification for leg in slip.legs):
                errors.append(f"Slip missing justification metadata: {slip.name}")
                continue
            seen.add(batter_key)
            deduped.append(slip)
        return deduped


def generate_slip_portfolio(cluster_report: ClusterRanking | None, user_config: RussWorksUserConfig | None = None) -> SlipPortfolio:
    return Step5SlipEngine(user_config=user_config).generate_slip_portfolio(cluster_report)


def generate_core_slips(cluster_report: ClusterRanking) -> List[Slip]:
    return Step5SlipEngine().generate_core_slips(cluster_report)


def generate_non_superstar_core_slips(cluster_report: ClusterRanking) -> List[Slip]:
    return Step5SlipEngine().generate_non_superstar_core_slips(cluster_report)


def generate_balanced_slips(cluster_report: ClusterRanking) -> List[Slip]:
    return Step5SlipEngine().generate_balanced_slips(cluster_report)


def generate_chaos_slips(cluster_report: ClusterRanking) -> List[Slip]:
    return Step5SlipEngine().generate_chaos_slips(cluster_report)


def generate_contrarian_slips(cluster_report: ClusterRanking) -> List[Slip]:
    return Step5SlipEngine().generate_contrarian_slips(cluster_report)


def _ranked_reports(cluster_report: ClusterRanking) -> List[TeamClusterReport]:
    return sorted(cluster_report.ranked_teams, key=lambda report: report.total_cluster_score, reverse=True)


def _unique_names(names: Iterable[str]) -> List[str]:
    unique: List[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return unique


def _leg(report: TeamClusterReport, batter: str, role: str, justification: str) -> SlipLeg:
    return SlipLeg(
        batter=batter,
        team=report.team,
        tag=report.tag_grade,
        cps=report.cps_grade,
        russ_score=report.total_cluster_score,
        slip_role=role,
        justification=justification,
    )


def _slip(
    *,
    name: str,
    slip_type: str,
    legs: Sequence[SlipLeg],
    justification: str,
    cluster: TeamClusterReport,
    min_legs: int = 2,
) -> Slip | None:
    unique_legs = _unique_legs(legs)
    if len(unique_legs) < min_legs:
        return None
    return Slip(
        name=name,
        slip_type=slip_type,
        legs=unique_legs,
        justification=justification,
        metadata={
            "team": cluster.team,
            "opponent": cluster.opponent,
            "cluster_strength": cluster.cluster_strength_label,
            "cluster_score": f"{cluster.total_cluster_score:.2f}",
            "ypi_grade": cluster.ypi_grade,
            "ypi_score": f"{cluster.ypi_score:.2f}",
            "veteran_bounce_grade": cluster.veteran_bounce_grade,
            "veteran_bounce_score": f"{cluster.veteran_bounce_score:.2f}",
            "catcher_power_grade": cluster.catcher_power_grade,
            "catcher_power_score": f"{cluster.catcher_power_score:.2f}",
            "pitch_mix_matchup_grade": cluster.pitch_mix_matchup_grade,
            "pitch_mix_matchup_score": f"{cluster.pitch_mix_matchup_score:.2f}",
            "bullpen_exposure_grade": cluster.bullpen_exposure_grade,
            "bullpen_exposure_score": f"{cluster.bullpen_exposure_score:.2f}",
            "park_factor_grade": cluster.park_factor_grade,
            "park_factor_score": f"{cluster.park_factor_score:.2f}",
        },
    )


def _unique_legs(legs: Sequence[SlipLeg]) -> List[SlipLeg]:
    unique: List[SlipLeg] = []
    seen: set[str] = set()
    for leg in legs:
        if leg.batter in seen:
            continue
        seen.add(leg.batter)
        unique.append(leg)
    return unique


def _all_report_names(report: TeamClusterReport) -> set[str]:
    return set(_unique_names([
        report.cluster_captain,
        report.hidden_cluster_beneficiary,
        *report.core_bats,
        *report.secondary_bats,
        *report.non_superstar_cluster_bats,
        *report.catcher_power_bats,
        *report.ypi_bats,
        *report.veteran_bounce_bats,
        *report.pitch_mix_matchup_bats,
        *report.bullpen_exposure_bats,
        *report.park_factor_bats,
    ]))
