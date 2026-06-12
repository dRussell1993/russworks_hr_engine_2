# Russ-Works v1.0 Formula Specification

## Purpose
Create a consistent, no-shortcuts HR analysis workflow that scores every batter and produces standardized Step 3, Step 4, Step 5, and post-mortem reports.

## Core modules

### LPAS — Lineup Position Advantage Score
Baseline lineup slot weights:
- #4: +15%
- #3: +12%
- #1: +10%
- #5: +7%
- #2: +5%
- #6: neutral
- #7: +8% only when TAG and CPS are A-level and offensive cluster conditions are present
- #8/#9: penalty unless exceptional collision/barrel/environment override exists

### TAG — Team Attack Grade
Team-level offensive attack score based on HR%, lineup concentration, park/weather, pitcher attackability, and top-half strength.

### CPS — Cluster Participation Score
Grades whether power production is concentrated or spread through the lineup.
Inputs:
- HR% concentration
- top 5 lineup score
- number of viable HR bats
- recent/post-mortem archetype alignment
- environment

### YPI — Young Power Index
Upgrade emerging bats with power signals, high HR%, weak-spot fit, and post-mortem carryover.

### Catcher Power Module
Catchers are explicitly surfaced because post-mortems showed catcher HRs outperform ownership.

### Veteran Bounce
Veteran power bats with strong LPAS/collision get a controlled boost.

### Weak-Spot Collision
Compares batter pitch/path profile to pitcher weak spots and HR matchup CSVs.

### Superstar Tax
Do not let name value crowd out YPI/value/cluster beneficiaries. Superstars still grade highly but get no automatic override unless collision and LPAS support it.

### Post-Mortem Learning
Winners and misses update logs. Daily review should check:
- YPI hit rate
- Catcher hit rate
- TAG/CPS hit rate
- LPAS hit rate
- weak-spot hit rate
- superstar false positives
- almost-made-it winners

## Required Step 2 inputs
- Game environment
- Umpire
- Starting pitchers
- Confirmed lineups
- Pitcher weak spots
- HR matchup files

No Step 3 can run without Step 2 validation.
