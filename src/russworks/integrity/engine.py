from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from russworks.data import DailySlate
from russworks.models import Handedness
from russworks.providers import ProviderHealth, ProviderResult

from .models import (
    DataIntegrityResult,
    IntegrityAlert,
    IntegrityReport,
    IntegritySeverity,
    ProviderIntegrityResult,
)


_VALID_HANDEDNESS = {item.value for item in Handedness}
_VALID_ROOFS = {"open", "closed", "retractable", "dome", "unknown"}


class IntegrityEngine:
    def validate_daily_slate(
        self,
        slate: DailySlate,
        *,
        provider_results: Iterable[ProviderResult] = (),
        provider_health: Iterable[ProviderHealth | Mapping[str, Any]] = (),
    ) -> IntegrityReport:
        data_results = [
            self.validate_slate_structure(slate),
            self.validate_lineups(slate),
            self.validate_pitchers(slate),
            self.validate_environment(slate),
            self.validate_umpires(slate),
            self.validate_matchup_inputs(slate),
        ]
        provider_integrity = [self.validate_provider_result(result) for result in provider_results]
        provider_integrity.extend(self.validate_provider_health(item) for item in provider_health)
        alerts = [alert for result in data_results for alert in result.alerts]
        alerts.extend(alert for result in provider_integrity for alert in result.alerts)
        return IntegrityReport(
            generated_at=_now(),
            date=slate.date,
            data_results=data_results,
            provider_results=provider_integrity,
            alerts=alerts,
        )

    def validate_slate_structure(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        if _blank(slate.date):
            alerts.append(_alert("ERROR", "missing_field", "Daily slate date is missing.", "slate.date", field="date", value=slate.date))
        if not slate.games:
            alerts.append(_alert("CRITICAL", "missing_field", "Daily slate has no games loaded.", "slate.games", field="games", value=0))

        seen_game_ids: set[str] = set()
        for game in slate.games:
            location = _game_location(game)
            if _blank(game.game_id):
                alerts.append(_alert("ERROR", "missing_field", "Game ID is missing.", location, field="game_id", value=game.game_id))
            elif game.game_id in seen_game_ids:
                alerts.append(_alert("ERROR", "duplicate_game", f"Duplicate game ID detected: {game.game_id}.", location, field="game_id", value=game.game_id))
            seen_game_ids.add(game.game_id)
            if _blank(game.date):
                alerts.append(_alert("WARNING", "missing_field", f"{game.game_id} game date is missing.", location, field="date", value=game.date))
            if _blank(game.away_team.team) or _blank(game.home_team.team):
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} is missing away or home team.", location, field="team"))
            if game.away_team.team and game.away_team.team == game.home_team.team:
                alerts.append(_alert("ERROR", "team_opponent_mismatch", f"{game.game_id} has the same away and home team: {game.away_team.team}.", location))
        return DataIntegrityResult(dataset="slate", checked_records=len(slate.games), alerts=alerts)

    def validate_lineups(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        checked = 0
        for game in slate.games:
            game_teams = {game.away_team.team, game.home_team.team}
            for team in game.teams:
                slots: dict[int, str] = {}
                player_names: set[str] = set()
                for batter in team.batters:
                    checked += 1
                    location = f"{game.game_id}.{team.team}.{batter.name or 'unknown_batter'}"
                    if _blank(batter.name):
                        alerts.append(_alert("ERROR", "missing_field", f"{team.team} has a batter with no name.", location, field="name", value=batter.name))
                    if _blank(batter.team):
                        alerts.append(_alert("ERROR", "missing_field", f"{batter.name or 'Unknown batter'} has no team.", location, field="team", value=batter.team))
                    elif batter.team != team.team:
                        alerts.append(_alert("ERROR", "team_opponent_mismatch", f"{batter.name} team {batter.team} does not match lineup team {team.team}.", location, field="team", value=batter.team))
                    elif batter.team not in game_teams:
                        alerts.append(_alert("ERROR", "team_opponent_mismatch", f"{batter.name} belongs to {batter.team}, which is not in {game.game_id}.", location, field="team", value=batter.team))

                    if batter.lineup_slot is None:
                        alerts.append(_alert("ERROR", "missing_field", f"{batter.name or team.team} is missing a lineup slot.", location, field="lineup_slot", value=batter.lineup_slot))
                    elif not isinstance(batter.lineup_slot, int) or isinstance(batter.lineup_slot, bool) or not 1 <= batter.lineup_slot <= 9:
                        alerts.append(_alert("ERROR", "out_of_range", f"{batter.name} has invalid lineup slot {batter.lineup_slot}.", location, field="lineup_slot", value=batter.lineup_slot))
                    else:
                        if batter.lineup_slot in slots:
                            alerts.append(
                                _alert(
                                    "ERROR",
                                    "duplicate_lineup_slot",
                                    f"{team.team} has duplicate lineup slot {batter.lineup_slot}: {slots[batter.lineup_slot]} and {batter.name}.",
                                    location,
                                    field="lineup_slot",
                                    value=batter.lineup_slot,
                                )
                            )
                        slots[batter.lineup_slot] = batter.name

                    normalized_name = _norm(batter.name)
                    if normalized_name:
                        if normalized_name in player_names:
                            alerts.append(_alert("ERROR", "duplicate_player", f"Duplicate batter in {team.team} lineup: {batter.name}.", location, field="name", value=batter.name))
                        player_names.add(normalized_name)

                    alerts.extend(_handedness_alerts(batter.bats, location, "bats"))
                    alerts.extend(_range_alerts(location, "hr_pct", batter.hr_pct, 0.0, 100.0))
                    alerts.extend(_range_alerts(location, "pitch_mix_score", batter.pitch_mix_score, 0.0, 10.0, severity="WARNING"))
                    alerts.extend(_range_alerts(location, "projected_ab", batter.projected_ab, 0, 8, severity="WARNING"))
                    alerts.extend(_range_alerts(location, "projected_hits", batter.projected_hits, 0.0, 8.0, severity="WARNING"))

                missing_slots = sorted(set(range(1, 10)) - set(slots))
                for slot in missing_slots:
                    alerts.append(_alert("ERROR", "missing_lineup_slot", f"{team.team} is missing lineup slot {slot}.", f"{game.game_id}.{team.team}", field="lineup_slot", value=slot))
        return DataIntegrityResult(dataset="lineups", checked_records=checked, alerts=alerts)

    def validate_pitchers(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        checked = 0
        for game in slate.games:
            for team in game.teams:
                pitcher = team.starting_pitcher
                location = f"{game.game_id}.{team.team}.starting_pitcher"
                if pitcher is None:
                    alerts.append(_alert("ERROR", "missing_field", f"{team.team} is missing starting pitcher data.", location, field="starting_pitcher"))
                    continue
                checked += 1
                if _blank(pitcher.name):
                    alerts.append(_alert("ERROR", "missing_field", f"{team.team} starting pitcher name is missing.", location, field="name", value=pitcher.name))
                if pitcher.team != team.team:
                    alerts.append(_alert("ERROR", "team_opponent_mismatch", f"{pitcher.name or 'Pitcher'} team {pitcher.team} does not match {team.team}.", location, field="team", value=pitcher.team))
                alerts.extend(_handedness_alerts(pitcher.throws, location, "throws"))
                for field in ("projected_ip", "projected_hits", "projected_hr", "projected_bb", "projected_er", "projected_outs"):
                    alerts.extend(_range_alerts(location, field, getattr(pitcher, field), 0.0, 30.0, severity="WARNING"))
        return DataIntegrityResult(dataset="pitchers", checked_records=checked, alerts=alerts)

    def validate_environment(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        checked = 0
        for game in slate.games:
            environment = game.environment
            location = f"{game.game_id}.environment"
            if environment is None:
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} is missing environment data.", location, field="environment"))
                continue
            checked += 1
            if environment.game_id != game.game_id:
                alerts.append(_alert("ERROR", "team_opponent_mismatch", f"Environment game ID {environment.game_id} does not match {game.game_id}.", location, field="game_id", value=environment.game_id))
            if environment.away_team != game.away_team.team or environment.home_team != game.home_team.team:
                alerts.append(
                    _alert(
                        "ERROR",
                        "team_opponent_mismatch",
                        f"Environment teams {environment.away_team}/{environment.home_team} do not match game teams {game.away_team.team}/{game.home_team.team}.",
                        location,
                    )
                )
            if _blank(environment.park):
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} park is missing.", location, field="park", value=environment.park))
            alerts.extend(_range_alerts(location, "temperature_f", environment.temperature_f, -20.0, 130.0))
            alerts.extend(_range_alerts(location, "wind_mph", environment.wind_mph, 0.0, 80.0))
            alerts.extend(_range_alerts(location, "humidity_pct", environment.humidity_pct, 0.0, 100.0))
            alerts.extend(_range_alerts(location, "weather_hr_pct", environment.weather_hr_pct, -50.0, 50.0, severity="WARNING"))
            alerts.extend(_range_alerts(location, "weather_distance_ft", environment.weather_distance_ft, -100.0, 100.0, severity="WARNING"))
            alerts.extend(_range_alerts(location, "park_hr_factor", environment.park_hr_factor, 0.0, 20.0))
            if str(environment.roof).strip().lower() not in _VALID_ROOFS:
                alerts.append(_alert("WARNING", "invalid_weather_value", f"{game.game_id} has unrecognized roof status {environment.roof}.", location, field="roof", value=environment.roof))
        return DataIntegrityResult(dataset="environment", checked_records=checked, alerts=alerts)

    def validate_umpires(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        checked = 0
        for game in slate.games:
            umpire = game.umpire or (game.environment.umpire if game.environment else None)
            location = f"{game.game_id}.umpire"
            if umpire is None:
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} is missing umpire data.", location, field="umpire"))
                continue
            checked += 1
            if _blank(umpire.name):
                alerts.append(_alert("WARNING", "missing_field", f"{game.game_id} umpire name is missing.", location, field="name", value=umpire.name))
            alerts.extend(_rate_or_percent_alerts(location, "called_strike_rate", umpire.called_strike_rate))
            alerts.extend(_rate_or_percent_alerts(location, "accuracy", umpire.accuracy))
            alerts.extend(_rate_or_percent_alerts(location, "consistency", umpire.consistency))
            alerts.extend(_range_alerts(location, "run_lean", umpire.run_lean, -5.0, 5.0, severity="WARNING"))
        return DataIntegrityResult(dataset="umpires", checked_records=checked, alerts=alerts)

    def validate_matchup_inputs(self, slate: DailySlate) -> DataIntegrityResult:
        alerts: list[IntegrityAlert] = []
        checked = 0
        for game in slate.games:
            if not game.weak_spots:
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} is missing weak spot data.", f"{game.game_id}.weak_spots", field="weak_spots"))
            if not game.hr_matchups:
                alerts.append(_alert("ERROR", "missing_field", f"{game.game_id} is missing HR matchup data.", f"{game.game_id}.hr_matchups", field="hr_matchups"))
            for index, weak_spot in enumerate(game.weak_spots):
                checked += 1
                location = f"{game.game_id}.weak_spots[{index}]"
                if _blank(weak_spot.pitcher_name):
                    alerts.append(_alert("ERROR", "missing_field", "Weak spot pitcher name is missing.", location, field="pitcher_name", value=weak_spot.pitcher_name))
                if _blank(weak_spot.pitch):
                    alerts.append(_alert("ERROR", "missing_field", "Weak spot pitch type is missing.", location, field="pitch", value=weak_spot.pitch))
                alerts.extend(_range_alerts(location, "weakness_score", weak_spot.weakness_score, 0.0, 10.0))
            for index, matchup in enumerate(game.hr_matchups):
                checked += 1
                location = f"{game.game_id}.hr_matchups[{index}]"
                if _blank(matchup.batter_name):
                    alerts.append(_alert("ERROR", "missing_field", "HR matchup batter name is missing.", location, field="batter_name", value=matchup.batter_name))
                if _blank(matchup.pitcher_name):
                    alerts.append(_alert("ERROR", "missing_field", "HR matchup pitcher name is missing.", location, field="pitcher_name", value=matchup.pitcher_name))
                alerts.extend(_range_alerts(location, "matchup_score", matchup.matchup_score, 0.0, 10.0))
                if matchup.exit_velo is not None:
                    alerts.extend(_range_alerts(location, "exit_velo", matchup.exit_velo, 0.0, 130.0, severity="WARNING"))
                if matchup.angle is not None:
                    alerts.extend(_range_alerts(location, "angle", matchup.angle, -90.0, 90.0, severity="WARNING"))
                if matchup.distance is not None:
                    alerts.extend(_range_alerts(location, "distance", matchup.distance, 0.0, 600.0, severity="WARNING"))
        return DataIntegrityResult(dataset="matchup_inputs", checked_records=checked, alerts=alerts)

    def validate_provider_result(self, result: ProviderResult) -> ProviderIntegrityResult:
        alerts: list[IntegrityAlert] = []
        if not result.success:
            severity = "ERROR" if result.dataset in {"lineups", "starting_pitchers", "probable_pitchers", "weather", "umpires"} else "WARNING"
            alerts.append(
                _alert(
                    severity,
                    "provider_failure",
                    f"{result.provider} failed to load {result.dataset}: {'; '.join(result.errors) or 'unknown error'}.",
                    f"provider.{result.provider}.{result.dataset}",
                    provider=result.provider,
                    field="success",
                    value=result.success,
                )
            )
        if result.success and not result.records:
            alerts.append(
                _alert(
                    "WARNING",
                    "provider_empty_dataset",
                    f"{result.provider} returned no records for {result.dataset}.",
                    f"provider.{result.provider}.{result.dataset}",
                    provider=result.provider,
                    field="records",
                    value=0,
                )
            )
        for index, record in enumerate(result.records):
            for field, value in record.items():
                if value is None:
                    alerts.append(_alert("WARNING", "null_value", f"{result.dataset} record has null field {field}.", f"provider.{result.provider}.{result.dataset}[{index}]", provider=result.provider, field=str(field), value=value))
        return ProviderIntegrityResult(provider=result.provider, dataset=result.dataset, checked_records=len(result.records), success=result.success, alerts=alerts)

    def validate_provider_health(self, item: ProviderHealth | Mapping[str, Any]) -> ProviderIntegrityResult:
        row = asdict(item) if is_dataclass(item) else dict(item)
        provider = str(row.get("provider", "provider"))
        status = str(row.get("status", "unknown"))
        alerts: list[IntegrityAlert] = []
        if status in {"error", "rate_limited", "not_configured"}:
            severity = "ERROR" if status == "error" else "WARNING"
            alerts.append(_alert(severity, "provider_health", f"{provider} health status is {status}.", f"provider.{provider}.health", provider=provider, field="status", value=status))
        elif status == "unknown":
            alerts.append(_alert("INFO", "provider_health", f"{provider} health status is unknown.", f"provider.{provider}.health", provider=provider, field="status", value=status))
        return ProviderIntegrityResult(provider=provider, dataset="health", checked_records=1, success=status not in {"error", "rate_limited"}, alerts=alerts)

    def export_json(self, report: IntegrityReport, output_dir: str | Path = "data/integrity") -> Path:
        output_path = Path(output_dir) / "integrity_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.to_json(), encoding="utf-8")
        return output_path


def validate_daily_slate(slate: DailySlate, **kwargs: Any) -> IntegrityReport:
    return IntegrityEngine().validate_daily_slate(slate, **kwargs)


def _alert(
    severity: str,
    category: str,
    message: str,
    location: str,
    *,
    provider: str = "",
    field: str = "",
    value: Any = None,
) -> IntegrityAlert:
    return IntegrityAlert(
        severity=IntegritySeverity(severity),
        category=category,
        message=message,
        location=location,
        provider=provider,
        field=field,
        value=value,
    )


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _game_location(game: Any) -> str:
    return f"game.{getattr(game, 'game_id', '') or 'unknown'}"


def _handedness_alerts(value: Any, location: str, field: str) -> list[IntegrityAlert]:
    raw = value.value if isinstance(value, Handedness) else str(value or "").strip().upper()
    if raw not in _VALID_HANDEDNESS:
        return [_alert("ERROR", "invalid_handedness", f"{location} has invalid handedness {value}.", location, field=field, value=value)]
    if raw == Handedness.UNKNOWN.value:
        return [_alert("WARNING", "invalid_handedness", f"{location} handedness is UNKNOWN.", location, field=field, value=raw)]
    return []


def _range_alerts(
    location: str,
    field: str,
    value: Any,
    minimum: float,
    maximum: float,
    *,
    severity: str = "ERROR",
) -> list[IntegrityAlert]:
    if value is None:
        return [_alert("WARNING", "null_value", f"{location}.{field} is null.", location, field=field, value=value)]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return [_alert("ERROR", "out_of_range", f"{location}.{field} is not numeric: {value}.", location, field=field, value=value)]
    if numeric < minimum or numeric > maximum:
        return [_alert(severity, "out_of_range", f"{location}.{field}={value} outside expected range {minimum}..{maximum}.", location, field=field, value=value)]
    return []


def _rate_or_percent_alerts(location: str, field: str, value: Any) -> list[IntegrityAlert]:
    if value in (None, ""):
        return [_alert("WARNING", "null_value", f"{location}.{field} is missing.", location, field=field, value=value)]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return [_alert("ERROR", "invalid_umpire_metric", f"{location}.{field} is not numeric: {value}.", location, field=field, value=value)]
    if numeric == 0:
        return []
    if 0.0 <= numeric <= 1.0 or 1.0 <= numeric <= 100.0:
        return []
    return [_alert("ERROR", "invalid_umpire_metric", f"{location}.{field}={value} is outside rate/percent bounds.", location, field=field, value=value)]


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
