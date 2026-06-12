# Russ-Works HR Engine

A Codex-ready Python scoring engine for the Hype Man Sports / Russ-Works MLB home-run workflow.

The engine enforces the step system:

1. **Step 1: Watchlist Intake**
2. **Step 2: Game Validation** — no Step 3 can run without environment, umpire, pitchers, lineups, weak spots, and HR matchup inputs.
3. **Step 3: Full Batter Review** — every batter is scored.
4. **Step 4: TAG/CPS Cluster Construction**
5. **Step 5: Slip Construction**
6. **Post-Mortem: Winners, Losers, False Positives, Adjustments**

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
python -m russworks.main --sample
```

## Input CSVs

See `/templates` for CSV templates.

## Core rule

Step 3 will fail if Step 2 is incomplete. This prevents shortcuts.
