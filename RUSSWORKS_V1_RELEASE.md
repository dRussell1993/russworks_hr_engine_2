# Russ-Works V1 Release Candidate

Date: 2026-06-13

Version: 1.0.0

Status: V1 release candidate

This document is the operator and developer handoff for Russ-Works HR Engine V1. It describes the final V1 architecture, daily workflow, required inputs, generated outputs, deployment path, scheduler behavior, post-mortem process, validation checklist, known limitations, and roadmap.

Phase 39 is documentation and release hardening only. It does not change formula logic, scoring logic, slip logic, or module weights.

## 1. Final Architecture Overview

Russ-Works is a phase-based MLB home-run analysis engine. The core workflow is:

1. Load daily slate data through CSV, JSON, or provider adapters.
2. Enforce Step 2 validation before any scoring runs.
3. Review every batter in Step 3.
4. Rank team clusters in Step 4.
5. Construct Step 5 slip portfolios.
6. Generate reports, explanations, risk analysis, simulations, dashboards, and command-center views.
7. Run post-mortem ingestion after games finish.
8. Calibrate, trend, optimize, and recommend without automatically changing weights.

Primary packages:

- `russworks.scoring`: Phase 1 scoring modules.
- `russworks.intake`: watchlist intake and Step 2 validation.
- `russworks.review`: Step 3 batter review engine.
- `russworks.cluster`: Step 4 cluster ranking.
- `russworks.slips`: Step 5 slip construction.
- `russworks.postmortem`: actual HR ingestion and comparison.
- `russworks.calibration`, `russworks.dashboard`, `russworks.recommendations`, `russworks.trends`, `russworks.optimizer`: learning and recommendation layers.
- `russworks.pipeline`: daily orchestration.
- `russworks.providers`: live/fallback provider scaffolding.
- `russworks.command_center`: operator status summary.
- `russworks.deployment`: runtime and container helpers.
- `russworks.scheduler`: autonomous task orchestration.
- `russworks.web`: dashboard-data presentation layer.
- `russworks.validate`: V1 startup self-test.

## 2. Completed Phases 1-38

1. Phase 1: Scoring engine with TAG, CPS, LSTM, PVS, Environment, and Umpire modules.
2. Phase 2: Watchlist intake layer and Step 2 validation gate.
3. Phase 3: Step 3 batter review engine.
4. Phase 4: Step 4 team cluster ranking.
5. Phase 5: Step 5 slip construction engine.
6. Phase 6: Post-mortem and calibration engine.
7. Phase 7: Weak-Spot Collision engine.
8. Phase 8: Young Power Index engine.
9. Phase 9: Veteran Bounce engine.
10. Phase 10: Catcher Power engine.
11. Phase 11: Pitch Mix Matchup engine.
12. Phase 12: Bullpen Exposure engine.
13. Phase 13: Live post-mortem ingestion layer.
14. Phase 14: Park Factor Engine V2.
15. Phase 15: full report generator.
16. Phase 16: MLB data connector layer for CSV and JSON imports.
17. Phase 17: historical backtesting engine.
18. Phase 18: formula calibration engine.
19. Phase 19: daily automation pipeline.
20. Phase 20: real MLB provider layer scaffolding.
21. Phase 21: calibration dashboard.
22. Phase 22: weight recommendation engine.
23. Phase 23: auto daily post-mortem runner.
24. Phase 24: historical trend engine.
25. Phase 25: formula optimizer.
26. Phase 26: production hardening, schema versioning, and CI.
27. Phase 27: operator command center.
28. Phase 28: user configuration layer.
29. Phase 29: explainability engine.
30. Phase 30: data integrity monitoring.
31. Phase 31: confidence engine.
32. Phase 32: portfolio and risk management.
33. Phase 33: exposure diversification engine.
34. Phase 34: Monte Carlo simulation engine.
35. Phase 35: self-learning recommendation layer.
36. Phase 36: deployment and containerization.
37. Phase 37: autonomous operations scheduler.
38. Phase 38: operator web dashboard data layer.

## 3. Module Dependency Map

Daily run dependencies:

- `configuration` loads user preferences and optional weight overrides.
- `data` and `providers` normalize watchlists, lineups, pitchers, weather, umpires, and park factors.
- `intake` validates the slate and blocks incomplete Step 2 runs.
- `review` depends on `scoring`, `confidence`, and specialty engines.
- `cluster` depends on Step 3 review output.
- `slips` depends on Step 4 cluster output.
- `reports` depends on Step 3, Step 4, Step 5, explainability, portfolio, diversification, simulation, and self-learning outputs.
- `pipeline` orchestrates the pre-game run.

Post-game dependencies:

- `postmortem` ingests actual HR data and compares against Step 5.
- `calibration` measures module performance.
- `dashboard` summarizes module and archetype health.
- `recommendations` suggests weight reviews without applying changes.
- `trends` classifies module direction.
- `optimizer` simulates recommendation scenarios.
- `automation` coordinates the post-mortem bundle.

Operator dependencies:

- `integrity` validates provider and slate quality.
- `command_center` summarizes slate status, formula health, execution state, and scheduler state.
- `scheduler` runs pre-slate, refresh, post-mortem, dashboard, and recommendation tasks.
- `deployment` loads environment-based runtime settings.
- `web` builds presentation-ready dashboard JSON.

## 4. Daily Operator Workflow

Pre-game:

1. Confirm data files or provider settings are ready.
2. Run `python -m russworks.validate`.
3. Run `python -m russworks.run --date YYYY-MM-DD`.
4. Review `data/outputs/YYYY-MM-DD/full_report.json`.
5. Review command-center, integrity, portfolio, diversification, simulation, and explanation exports.

Post-game:

1. Place actual HR data for the date into the post-mortem input path.
2. Run `python -m russworks.postmortem.run --date YYYY-MM-DD`.
3. Review post-mortem, dashboard, recommendations, trends, and optimizer exports.
4. Capture manual formula notes. Do not auto-apply recommendations.

Scheduled:

1. Run deployment validation before scheduled operations.
2. Run `python -m russworks.deployment.runtime --run-scheduler` or invoke the scheduler from a host orchestrator.
3. Review `data/scheduler/scheduler_status.json`.

## 5. Required Daily Inputs

Required pre-game inputs:

- Watchlist.
- Confirmed or probable lineups.
- Starting or probable pitchers.
- Weather/environment.
- Umpires.
- Park factors.
- Weak-spot data.
- HR matchup data.

Required post-game inputs:

- Actual home runs for the date.
- Batter.
- Team.
- Pitch.
- Pitcher.
- Inning.
- Exit velocity.
- Distance.
- Launch angle.

## 6. Generated Outputs

Core outputs:

- `data/outputs/YYYY-MM-DD/full_report.json`
- `data/integrity/integrity_report.json`
- `data/explanations/explanations.json`
- `data/portfolio/portfolio_report.json`
- `data/diversification/diversification_report.json`
- `data/simulation/simulation_report.json`
- `data/self_learning/self_learning_report.json`

Post-mortem and learning outputs:

- `data/postmortem/YYYY-MM-DD/`
- `data/dashboard/dashboard.json`
- `data/recommendations/recommendations.json`
- `data/trends/trends.json`
- `data/optimizer/optimizer_report.json`

Operator outputs:

- `data/command_center/command_center.json`
- `data/scheduler/scheduler_status.json`
- `dashboard_data.json`

## 7. Deployment Guide

Local setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m russworks.validate
```

Docker setup:

```bash
cp .env.example .env
docker compose run --rm russworks-validate
docker compose run --rm russworks-daily
```

Deployment runtime checks:

```bash
python -m russworks.deployment.runtime --validate-only
python -m russworks.validate
```

Mounts:

- `./data:/app/data`
- `./config:/app/config:ro`

## 8. Scheduler Guide

The scheduler tracks six V1 task families:

- Pre-slate run.
- Midday refresh.
- Lineup confirmation refresh.
- End-of-day post-mortem.
- Dashboard refresh.
- Recommendation refresh.

Run once:

```bash
python -m russworks.deployment.runtime --run-scheduler
```

The scheduler writes `data/scheduler/scheduler_status.json`. For V1, use host cron, Windows Task Scheduler, GitHub Actions, or another orchestrator to run it on a clock.

## 9. Post-Mortem Guide

Manual CSV imports are supported first. Live API provider support remains scaffolded for future hardening.

Run:

```bash
python -m russworks.postmortem.run --date YYYY-MM-DD
```

The runner should:

- Load actual HR entries.
- Load the generated Step 5 report or slips.
- Compare portfolio hits and misses.
- Update calibration, dashboard, recommendations, trends, and optimizer outputs.
- Preserve duplicate HRs by the same batter.
- Preserve historical files.

## 10. Troubleshooting Guide

Common failures:

- Step 2 incomplete: inspect missing-data messages in the daily pipeline result.
- Missing lineups: check lineup CSV or provider result for each team.
- Missing pitcher data: confirm starters/probables include game IDs and teams.
- Missing environment or umpire data: check weather and umpire input files.
- Provider not configured: set provider base URL environment variables or use CSV mode.
- Report loading failure: verify `schema_version` and required `context`, `step3`, `step4`, and `step5` sections.
- Scheduler failures: inspect `data/scheduler/scheduler_status.json`.

## 11. Recovery Procedures

If pre-game validation fails:

1. Do not run Step 3 manually.
2. Fix missing or malformed input data.
3. Run `python -m russworks.validate`.
4. Re-run `python -m russworks.run --date YYYY-MM-DD`.

If post-mortem fails:

1. Confirm actual HR input exists.
2. Confirm generated report exists for the same date.
3. Re-run the post-mortem command.
4. Preserve failed output folders for debugging.

If scheduler fails:

1. Review failed task errors.
2. Run the failed command manually.
3. Re-run scheduler after input or config correction.

## 12. Provider Configuration Guide

CSV mode is the default and requires no paid API keys.

Environment variables:

- `RUSSWORKS_PROVIDER_MODE`: `csv` or `live`.
- `RUSSWORKS_MLB_STATS_BASE_URL`: live lineups, pitchers, and umpires.
- `RUSSWORKS_BASEBALL_SAVANT_BASE_URL`: future statcast-style data.
- `RUSSWORKS_WEATHER_BASE_URL`: live weather data.
- `RUSSWORKS_BALLPARK_BASE_URL`: live ballpark data.
- `RUSSWORKS_PROVIDER_TIMEOUT_SECONDS`: provider timeout.
- `RUSSWORKS_PROVIDER_MAX_RETRIES`: provider retry count.

Provider keys must be supplied through environment variables when needed. Do not hardcode keys in source files or committed config.

## 13. Validation Checklist

Startup self-test:

```bash
python -m russworks.validate
```

Release validation checklist:

- Imports succeed for pipeline, providers, scheduler, reports, dashboard, command center, deployment, and web modules.
- Config loads from `config/russworks_config.yaml` or defaults.
- Scheduler exposes all six default tasks.
- Provider package exports registered provider classes and result models.
- Report generator emits schema version `1.0`.
- Deployment runtime validation passes.
- Unit tests pass.
- No formula weights changed.
- No scoring logic changed.

## 14. Known Limitations

- Live provider adapters are scaffolded and require concrete endpoint configuration.
- Some legacy top-level modules still coexist with the modern phase architecture.
- Analytics outputs are file-based and not concurrency-safe for multiple simultaneous runs.
- Backtesting is serial and local-file oriented.
- Recommendations, optimizer results, and self-learning insights are advisory only.
- No database, UI server, or paid API integration is included in V1.

## 15. Future Roadmap

Recommended next work:

1. Harden concrete MLB provider adapters with contract fixtures.
2. Quarantine or retire legacy top-level modules.
3. Centralize module registry, weights, thresholds, and display names.
4. Add structured logging, run IDs, and atomic JSON writes.
5. Add immutable historical output conventions.
6. Add database support only after file schemas stabilize.
7. Add production-grade web UI on top of `dashboard_data.json`.
8. Expand CI with type checking and realistic slate fixtures.
9. Add performance tests for season-scale backtesting.
10. Reconcile implemented defaults with the formula spec after calibration data matures.
