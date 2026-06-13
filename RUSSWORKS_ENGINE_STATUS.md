# Russ-Works HR Engine Status

Last updated: 2026-06-13

This document is the working milestone map for the Russ-Works HR Engine. It summarizes the completed phases, major modules, CLI entry points, data flow, generated artifacts, and future roadmap so future development can move faster without re-reading the full history.

## Engine Purpose

The Russ-Works HR Engine is a no-shortcuts MLB home-run analysis system. It ingests watchlists, lineups, pitcher data, environment context, umpire data, weak spots, and HR matchup inputs; validates that every required piece exists; reviews every batter; ranks team clusters; builds slip portfolios; and learns from post-mortems, calibration, trends, recommendations, and optimizer reports.

Core rule: Step 3 cannot run unless Step 2 validation passes. Every confirmed batter must be reviewed.

## Completed Phases

| Phase | Status | Summary | Primary Output |
|---|---|---|---|
| 1 | Complete | Built the config-driven scoring foundation for TAG, CPS, LSTM, PVS, Environment, and Umpire scoring. | `src/russworks/scoring/`, `src/russworks/models/`, `src/russworks/config/weights.py` |
| 2 | Complete | Added watchlist intake, batter/team/game intake models, Step 2 validation, and review queue generation. | `src/russworks/intake/` |
| 3 | Complete | Built the Step 3 Batter Review Engine and full per-batter Russ Score review objects. | `src/russworks/review/` |
| 4 | Complete | Built Step 4 Cluster Ranking with TAG/CPS-driven team cluster reports and special archetype identification. | `src/russworks/cluster/` |
| 5 | Complete | Built Step 5 Slip Construction with core, non-superstar, balanced, chaos, and contrarian slips. | `src/russworks/slips/` |
| 6 | Complete | Built Post-Mortem and Calibration logs for winners, losers, false positives, adjustments, and recommendations. | `src/russworks/postmortem/` |
| 7 | Complete | Added Weak-Spot Collision scoring and integrated it into Step 3. | `src/russworks/scoring/weakspot.py` |
| 8 | Complete | Added Young Power Index (YPI) scoring and integrated it through review, cluster, slips, and post-mortem analysis. | `src/russworks/scoring/ypi.py` |
| 9 | Complete | Added Veteran Bounce scoring and integrated it through review, cluster, slips, and post-mortem analysis. | `src/russworks/scoring/veteran.py` |
| 10 | Complete | Added Catcher Power scoring and integrated it through review, cluster, slips, and post-mortem analysis. | `src/russworks/scoring/catcher.py` |
| 11 | Complete | Added Pitch Mix Matchup scoring and integrated it through review, cluster, slips, and post-mortem analysis. | `src/russworks/scoring/pitchmix.py` |
| 12 | Complete | Added Bullpen Exposure scoring and integrated bullpen archetype tracking. | `src/russworks/scoring/bullpen.py` |
| 13 | Complete | Added live post-mortem ingestion layer with CSV imports and future MLB Stats provider placeholder. | `src/russworks/postmortem/ingestion.py`, `src/russworks/postmortem/run.py` |
| 14 | Complete | Added Park Factor V2 scoring with handedness, pull-side, weather, roof, and carry context. | `src/russworks/scoring/parkfactor.py` |
| 15 | Complete | Added Full Report Generator for Step 3, Step 4, Step 5, metadata, and JSON export. | `src/russworks/reports.py` |
| 16 | Complete | Added MLB Data Connector Layer for CSV/JSON watchlists, lineups, pitchers, weather, umpires, and park factors. | `src/russworks/data/` |
| 17 | Complete | Added Historical Backtesting Engine with date-range summaries and post-mortem comparison. | `src/russworks/backtesting/` |
| 18 | Complete | Added Formula Calibration Engine to measure module effectiveness and recommend adjustments without changing weights. | `src/russworks/calibration/` |
| 19 | Complete | Added Daily Automation Pipeline to load slate, validate, run Steps 3-5, generate full report, and save output. | `src/russworks/pipeline/`, `src/russworks/run.py` |
| 20 | Complete | Added real MLB provider architecture with provider results, health checks, retries, fallbacks, and env-var support. | `src/russworks/providers/` |
| 21 | Complete | Added Calibration Dashboard for module performance, trends, archetype performance, and dashboard JSON export. | `src/russworks/dashboard/` |
| 22 | Complete | Added Weight Recommendation Engine to suggest module weight movement with confidence, sample gates, and noise rejection. | `src/russworks/recommendations/` |
| 23 | Complete | Added Auto Daily Post-Mortem Runner to load actual HRs and generated reports, run post-mortem, calibration, dashboard, and recommendations. | `src/russworks/automation/` |
| 24 | Complete | Added Historical Trend Engine with 7-day, 14-day, 30-day, and season trend classification. | `src/russworks/trends/` |
| 25 | Complete | Added Formula Optimizer to simulate weight changes, estimate impact, reject noisy data, and export optimizer reports. | `src/russworks/optimizer/` |

## Major Module Map

### Core Models

- `src/russworks/models/`
  - Batter, team, game, score, tier, environment, umpire, weak spot, and matchup primitives.
- `src/russworks/intake/`
  - Watchlist, batter intake, team intake, game intake, validation queue, and Step 2 gate.
- `src/russworks/config/weights.py`
  - Default scoring weights for TAG, CPS, LSTM, Environment, Umpire, and PVS.

### Scoring Engines

- `tag.py`: Team Attack Grade.
- `cps.py`: Cluster Participation Score.
- `lstm.py`: Lineup Slot Trend Multiplier.
- `pvs.py`: Pitch Vulnerability Score.
- `environment.py`: Weather, park, roof, wind, temperature, and carry context.
- `umpire.py`: Umpire zone/run environment context.
- `weakspot.py`: Pitcher weak-zone and batter strength collision.
- `ypi.py`: Young Power Index.
- `veteran.py`: Veteran Bounce.
- `catcher.py`: Catcher Power.
- `pitchmix.py`: Batter vs pitcher pitch mix collision.
- `bullpen.py`: Bullpen exposure and relief risk.
- `parkfactor.py`: Park Factor V2.

### Workflow Engines

- `src/russworks/review/`: Step 3 Batter Review.
- `src/russworks/cluster/`: Step 4 Cluster Ranking.
- `src/russworks/slips/`: Step 5 Slip Construction.
- `src/russworks/reports.py`: Full report objects and JSON export.
- `src/russworks/pipeline/`: Daily pipeline orchestration.
- `src/russworks/automation/`: Auto daily post-mortem orchestration.

### Learning, Analysis, and Optimization

- `src/russworks/postmortem/`
  - Actual HR ingestion, post-mortem comparison, winner/loser/false-positive/adjustment logs.
- `src/russworks/backtesting/`
  - Historical slate execution and date-range performance summaries.
- `src/russworks/calibration/`
  - Module effectiveness metrics and calibration recommendations.
- `src/russworks/dashboard/`
  - Dashboard-level module performance, archetype success, and trend summaries.
- `src/russworks/recommendations/`
  - Weight recommendation reports. Recommendations only; live weights are not changed.
- `src/russworks/trends/`
  - Historical trend classifications: Heating Up, Stable, Cooling Off.
- `src/russworks/optimizer/`
  - Formula optimization scenarios and simulated weight impact. Recommendations only; live weights are not changed.

### Data and Provider Layer

- `src/russworks/data/`
  - CSV/JSON data providers for daily slate loading.
- `src/russworks/providers/`
  - Real provider architecture for MLB Stats, Baseball Savant, Weather, and Ballpark data with health and fallback support.

## CLI Commands

### Package Script

```bash
russworks --sample
```

Equivalent module entry:

```bash
python -m russworks.main --sample
```

### Daily Pipeline

Run a daily slate through validation, Step 3, Step 4, Step 5, and full report export:

```bash
python -m russworks.run --date YYYY-MM-DD
```

Optional CSV roots:

```bash
python -m russworks.run --date YYYY-MM-DD --data-root data/daily --output-root data/outputs
```

Output:

```text
data/outputs/YYYY-MM-DD/russworks_full_report.json
```

### Post-Mortem Ingestion

Normalize manual actual HR CSV imports:

```bash
python -m russworks.postmortem.run --date YYYY-MM-DD --csv data/postmortem/actual_home_runs_raw_YYYY-MM-DD.csv
```

Output:

```text
data/postmortem/actual_home_runs_YYYY-MM-DD.csv
```

### Auto Daily Post-Mortem

Run post-mortem automation using existing actual HR data and the generated daily report:

```bash
python -m russworks.postmortem.run --date YYYY-MM-DD
```

Optional explicit paths:

```bash
python -m russworks.postmortem.run \
  --date YYYY-MM-DD \
  --report-path data/outputs/YYYY-MM-DD/russworks_full_report.json \
  --output-dir data/postmortem \
  --dashboard-dir data/dashboard \
  --recommendations-dir data/recommendations
```

Outputs:

```text
data/postmortem/YYYY-MM-DD/postmortem_report.json
data/postmortem/YYYY-MM-DD/calibration_result.json
data/postmortem/YYYY-MM-DD/run_metadata.json
data/dashboard/dashboard.json
data/recommendations/recommendations.json
```

## Data Flow

```text
Step 1 Intake
  -> watchlist, lineups, pitchers, environment, umpires, weak spots, HR matchups

Step 2 Validation
  -> ReviewQueue
  -> blocks Step 3 if required data is missing

Step 3 Batter Review
  -> BatterReviewResult
  -> every confirmed batter gets Russ Score, tier, module scores, and archetype flags

Step 4 Cluster Ranking
  -> ClusterRanking
  -> team cluster reports using TAG/CPS as primary drivers

Step 5 Slip Construction
  -> SlipPortfolio
  -> core, non-superstar core, balanced, chaos, and contrarian slips

Full Report
  -> russworks_full_report.json

Actual HR Ingestion
  -> normalized actual_home_runs_YYYY-MM-DD.csv

Auto Post-Mortem
  -> compares Step 5 portfolio to actual HRs
  -> winner, loser, false-positive, adjustment, and recommendation logs

Calibration
  -> module metrics and recommended adjustments

Dashboard
  -> module performance, top/worst modules, archetype success

Weight Recommendations
  -> current vs suggested module weights
  -> no live weight changes

Historical Trends
  -> 7-day, 14-day, 30-day, season trend classification

Formula Optimizer
  -> simulated weight scenarios and expected impact
  -> no live weight changes
```

## Required Daily Inputs

The CSV/JSON connector layer currently expects daily slate inputs such as:

- Watchlists
- Confirmed lineups
- Starting or probable pitchers
- Weather/environment
- Umpires
- Park factors
- Pitcher weak spots
- HR matchup data

Step 2 validation reports every missing field and blocks Step 3 until the slate is complete enough for no-shortcuts review.

## Generated Artifacts

### Daily Pipeline

```text
data/outputs/YYYY-MM-DD/russworks_full_report.json
```

### Post-Mortem

```text
data/postmortem/actual_home_runs_YYYY-MM-DD.csv
data/postmortem/YYYY-MM-DD/postmortem_report.json
data/postmortem/YYYY-MM-DD/calibration_result.json
data/postmortem/YYYY-MM-DD/run_metadata.json
```

### Analysis

```text
data/dashboard/dashboard.json
data/recommendations/recommendations.json
data/trends/trends.json
data/optimizer/optimizer_report.json
```

## Guardrails

- Step 3 never runs if Step 2 validation is incomplete.
- Every confirmed batter must be reviewed.
- Slip generation requires Step 4 cluster results.
- Post-mortem requires actual HR entries and a Step 5 slip portfolio.
- Calibration, recommendations, trends, and optimizer reports are advisory only.
- Live weights are never automatically modified.
- Sample-size gates and noisy-data rejection prevent premature formula changes.
- Historical logs are preserved and date-scoped where appropriate.

## Testing Pattern

The repo currently uses plain Python test functions in `tests/test_*.py`. A lightweight runner imports each test file and executes zero-argument functions whose names start with `test_`.

Typical local test command used during development:

```powershell
$env:PYTHONPATH='src'
$python = 'C:\Users\Darren.Russell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -c "<test runner script>"
```

The test suite has grown alongside the phases and covers scoring, validation, review, cluster ranking, slip construction, post-mortem, ingestion, reporting, data connectors, backtesting, calibration, dashboard, recommendations, automation, trends, and optimizer behavior.

## Current Architecture Strengths

- Strongly typed dataclasses across the engine.
- Modular scoring engines with focused unit tests.
- Clear Step 2 validation gate.
- End-to-end daily pipeline from slate to JSON report.
- Structured post-mortem learning loop.
- Advisory calibration/recommendation/optimization layers that avoid unsafe automatic weight changes.
- Provider architecture ready for live data expansion without hardcoded API keys.

## Known Gaps and Future Roadmap

### Near-Term

- Add richer CSV/JSON fixtures for full multi-game slate testing.
- Persist trend and optimizer outputs from the auto post-mortem runner.
- Add CLI flags for trends and optimizer report generation.
- Improve typed loaders for saved report JSON instead of reconstructing objects inline.
- Add stronger date-range historical fixture support.

### Data Quality

- Harden live provider implementations once free/reliable endpoints are selected.
- Add provider-specific rate-limit telemetry to report metadata.
- Add schema validation for every daily input file.
- Add clearer error categories for missing vs stale vs low-confidence data.

### Formula Calibration

- Define exact sample-size thresholds for manual weight changes.
- Add accepted/rejected calibration decision logs.
- Track module performance by park, team, pitcher, handedness, and lineup slot.
- Separate normal baseball variance from true formula misses.

### Reporting

- Add markdown or CSV exports for Step 3, Step 4, Step 5, post-mortem, dashboard, trends, and optimizer reports.
- Add compact daily operator summary.
- Add historical comparison reports across date ranges.

### Product/UI

- Build a lightweight CLI menu or local dashboard after engine stability.
- Add visual dashboard support for module performance, trends, and optimizer scenarios.
- Add import/export workflows for manual review and correction.

### Long-Term

- Add database persistence for historical slates, reports, post-mortems, and calibration decisions.
- Add scheduling for daily run and post-mortem automation.
- Add richer player-level and pitch-level data models.
- Add controlled manual approval workflow for weight updates.
- Add versioned formula profiles so experiments can be compared safely.

## Developer Notes

- Keep new features small and phase-scoped.
- Prefer adding structured models over loose dictionaries when a concept becomes reusable.
- Preserve compatibility with the existing no-shortcuts workflow.
- Treat optimizer and recommendation outputs as advisory until a manual approval layer exists.
- Update this document after major milestones so it remains the first-stop map for future development.
