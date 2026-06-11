# Codex Task: Build Russ-Works HR Engine

You are working in this repository. Complete the Russ-Works v1 app from the provided scaffold.

## Objective
Build a Python engine that ingests MLB HR watchlist/game data and generates standardized Russ-Works Step 1–5 reports plus post-mortem logs.

## Hard requirements
1. Do not allow Step 3 unless Step 2 validation passes.
2. Every batter in the lineup must be reviewed in Step 3.
3. Reports must preserve this format:
   - Game header
   - Team vs pitcher table
   - TAG/CPS summaries
   - Gold/Silver/Bronze pools
   - YPI board
   - Catcher Power board
4. Post-mortem must output structured:
   - Winners Log
   - Losers Log
   - False Positive Log
   - Adjustment Log
5. Preserve the Russ-Works modules in `RUSS_WORKS_SPEC.md`.

## Build tasks
- Add a loader that builds a Game from a folder of CSVs.
- Add tests for Step 2 validation.
- Add tests that all batters are scored.
- Add an adjustment config file so formula weights can be changed after post-mortems.
- Add a CLI command:
  `russworks run --input data/inputs/TEX-KC-2026-06-11 --out data/outputs/TEX-KC.md`
- Add a CLI command:
  `russworks postmortem --input data/logs/results.csv --out data/outputs/postmortem.md`

## Do not build UI yet.
Focus on engine correctness, repeatable outputs, and logs.
