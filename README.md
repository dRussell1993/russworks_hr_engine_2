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

## V1 Release Validation

Phase 39 adds a startup self-test for release-candidate validation:

```bash
python -m russworks.validate
```

The self-test verifies package imports, user configuration loading, scheduler
loading, provider registration, and schema-versioned report generation.

## Live Slate Builder

Phase 40 adds a provider-driven slate builder that writes daily CSV inputs before
the normal pipeline runs:

```bash
python -m russworks.build_slate --date YYYY-MM-DD
python -m russworks.run --date YYYY-MM-DD --build-slate
```

The builder exports `watchlist.csv`, `lineups.csv`, `pitchers.csv`,
`weather.csv`, `umpires.csv`, `park_factors.csv`, `weak_spots.csv`, and
`hr_matchups.csv` under `data/daily/YYYY-MM-DD/`.

Successful daily runs also export operator runtime files:

- `data/dashboard/dashboard.json`
- `data/command_center/command_center.json`
- `data/web/dashboard_data.json`

## Local Web Dashboard

Phase 44 adds a Streamlit operator dashboard for local review of generated
Russ-Works outputs.

First run the daily pipeline so the JSON and markdown outputs exist:

```bash
python -m russworks.run --date YYYY-MM-DD
```

Then launch the local dashboard:

```bash
python -m russworks.ui.app
```

The dashboard reads:

- `data/web/dashboard_data.json`
- `data/outputs/YYYY-MM-DD/russworks_operator_report.md`
- `data/command_center/command_center.json`
- `data/dashboard/dashboard.json`

Dashboard pages:

- Overview
- Top HR Targets
- Team Clusters
- Step 5 Slips
- Confidence / Risk
- Validation Warnings
- Command Center

## Input CSVs

See `/templates` for CSV templates.

## Core rule

Step 3 will fail if Step 2 is incomplete. This prevents shortcuts.

## Deployment

Phase 36 adds container support for local and production-style runtime use.

### Local Docker Run

```bash
cp .env.example .env
docker compose run --rm russworks-validate
docker compose run --rm russworks-daily
```

Set `RUSSWORKS_RUN_DATE=YYYY-MM-DD` in `.env` before running the daily service.

### Runtime Configuration

The container reads environment variables for runtime mode, provider mode, data
paths, output paths, schedule metadata, and optional live provider URLs/API keys.
CSV mode is the default and does not require paid APIs.

Important variables:

- `RUSSWORKS_RUNTIME_MODE`: `local` or `production`
- `RUSSWORKS_PROVIDER_MODE`: `csv` or `live`
- `RUSSWORKS_RUN_DATE`: daily slate date
- `RUSSWORKS_DATA_ROOT`: mounted daily input root
- `RUSSWORKS_OUTPUT_ROOT`: mounted report output root
- `RUSSWORKS_CONFIG_PATH`: mounted user config path
- `RUSSWORKS_REPORT_VOLUME`: mounted report volume root

### Volumes

The compose setup mounts:

- `./data:/app/data`
- `./config:/app/config:ro`

Daily reports are written under `data/outputs/YYYY-MM-DD/`. Sidecar outputs are
written under `data/integrity/`, `data/portfolio/`, `data/diversification/`,
`data/simulation/`, and `data/self_learning/`.

### Scheduled Execution

The image does not run a scheduler daemon. Use host cron, Task Scheduler, GitHub
Actions, or another orchestrator to call:

```bash
docker compose run --rm russworks-daily
```

`RUSSWORKS_SCHEDULE_ENABLED` and `RUSSWORKS_DAILY_RUN_TIME_UTC` are stored as
runtime metadata for operators and future schedulers.

The autonomous scheduler can also be run once through the deployment runtime:

```bash
python -m russworks.deployment.runtime --run-scheduler
```

Scheduler status is exported to `data/scheduler/scheduler_status.json`.
