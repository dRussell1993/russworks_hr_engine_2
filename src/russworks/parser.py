from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List

from .models import Batter, GameEnvironment, Handedness, HRMatchup, Pitcher, PitcherWeakSpot, Umpire
from .data import normalize_game_id


def _hand(value: str) -> Handedness:
    value = (value or "").strip().upper()
    if value in {"L", "R", "S"}:
        return Handedness(value)
    return Handedness.UNKNOWN


def read_csv(path: str | Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_batters(path: str | Path) -> List[Batter]:
    rows = read_csv(path)
    batters: List[Batter] = []
    for r in rows:
        tags = [x.strip() for x in (r.get("tags") or "").split("|") if x.strip()]
        batters.append(Batter(
            name=r["name"],
            team=r["team"],
            bats=_hand(r.get("bats", "")),
            lineup_slot=int(float(r.get("lineup_slot") or 0)),
            hr_pct=float(r.get("hr_pct") or 0),
            pitch_mix_score=float(r.get("pitch_mix_score") or 0),
            projected_ab=int(float(r.get("projected_ab") or 4)),
            projected_hits=float(r.get("projected_hits") or 0),
            fair_odds=int(r["fair_odds"]) if r.get("fair_odds") else None,
            book_odds=int(r["book_odds"]) if r.get("book_odds") else None,
            tags=tags,
            confirmed=(r.get("confirmed", "true").lower() != "false"),
        ))
    return batters


def parse_pitchers(path: str | Path) -> Dict[str, Pitcher]:
    rows = read_csv(path)
    pitchers: Dict[str, Pitcher] = {}
    for r in rows:
        tags = [x.strip() for x in (r.get("tags") or "").split("|") if x.strip()]
        p = Pitcher(
            name=r["name"],
            team=r["team"],
            throws=_hand(r.get("throws", "")),
            tags=tags,
            projected_ip=float(r.get("projected_ip") or 0),
            projected_hits=float(r.get("projected_hits") or 0),
            projected_hr=float(r.get("projected_hr") or 0),
            projected_bb=float(r.get("projected_bb") or 0),
            projected_er=float(r.get("projected_er") or 0),
            projected_outs=float(r.get("projected_outs") or 0),
        )
        pitchers[p.name] = p
    return pitchers


def parse_environment(path: str | Path) -> GameEnvironment:
    rows = read_csv(path)
    if not rows:
        raise ValueError("environment CSV is empty")
    r = rows[0]
    ump = Umpire(
        name=r.get("umpire_name", ""),
        zone_type=r.get("umpire_zone_type", "Neutral"),
        called_strike_rate=float(r.get("called_strike_rate") or 0),
        accuracy=float(r.get("accuracy") or 0),
        consistency=float(r.get("consistency") or 0),
        run_lean=float(r.get("run_lean") or 0),
    )
    return GameEnvironment(
        game_id=normalize_game_id(r["game_id"]),
        date=r["date"],
        away_team=r["away_team"],
        home_team=r["home_team"],
        park=r["park"],
        temperature_f=float(r.get("temperature_f") or 70),
        wind_mph=float(r.get("wind_mph") or 0),
        wind_direction=r.get("wind_direction", ""),
        humidity_pct=float(r.get("humidity_pct") or 0),
        roof=r.get("roof", "open"),
        weather_hr_pct=float(r.get("weather_hr_pct") or 0),
        weather_distance_ft=float(r.get("weather_distance_ft") or 0),
        park_hr_factor=float(r.get("park_hr_factor") or 0),
        umpire=ump,
        original_game_id=r["game_id"],
    )


def parse_weak_spots(path: str | Path) -> List[PitcherWeakSpot]:
    rows = read_csv(path)
    out = []
    for r in rows:
        out.append(PitcherWeakSpot(
            pitcher_name=r.get("pitcher_name") or r.get("Pitcher") or "",
            pitch=r.get("pitch") or r.get("Pitch") or "",
            zone=r.get("zone") or r.get("Zone"),
            weakness_score=float(r.get("weakness_score") or r.get("score") or 0),
            notes=r.get("notes") or "",
            original_game_id=r.get("game_id") or r.get("game") or "",
        ))
    return out


def parse_hr_matchups(path: str | Path) -> List[HRMatchup]:
    rows = read_csv(path)
    out = []
    for r in rows:
        out.append(HRMatchup(
            batter_name=r.get("batter_name") or r.get("Batter") or "",
            pitcher_name=r.get("pitcher_name") or r.get("Pitcher") or "",
            pitch=r.get("pitch") or r.get("Pitch") or "",
            matchup_score=float(r.get("matchup_score") or r.get("score") or 0),
            exit_velo=float(r.get("exit_velo") or r.get("Exit Velo") or 0) or None,
            angle=float(r.get("angle") or r.get("Angle") or 0) or None,
            distance=float(r.get("distance") or r.get("Distance") or 0) or None,
            notes=r.get("notes") or "",
            original_game_id=r.get("game_id") or r.get("game") or "",
        ))
    return out
