from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

from .models import PostMortemEntry


FIELDS = ["date", "batter", "team", "result", "formula_status", "step3_score", "cluster_score", "pitch", "pitcher", "notes"]


def save_postmortem_entries(entries: Iterable[PostMortemEntry], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        for e in entries:
            writer.writerow({k: getattr(e, k) for k in FIELDS})


def load_postmortem_entries(path: str | Path) -> List[PostMortemEntry]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    entries = []
    for r in rows:
        entries.append(PostMortemEntry(
            date=r["date"],
            batter=r["batter"],
            team=r["team"],
            result=r["result"],
            formula_status=r.get("formula_status", ""),
            step3_score=float(r["step3_score"]) if r.get("step3_score") else None,
            cluster_score=float(r["cluster_score"]) if r.get("cluster_score") else None,
            pitch=r.get("pitch") or None,
            pitcher=r.get("pitcher") or None,
            notes=r.get("notes", ""),
        ))
    return entries
