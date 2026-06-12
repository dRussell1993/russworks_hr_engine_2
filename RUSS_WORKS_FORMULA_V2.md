# Russ-Works Formula V2 Specification

## Purpose

Russ-Works Formula V2 defines a no-shortcuts MLB home-run analysis workflow. It turns watchlist and game data into repeatable Step 1 through Step 5 outputs, then uses post-mortem logs to improve future scoring.

This specification is based on `README.md`, `RUSS_WORKS_SPEC.md`, and `CODEX_TASK_PROMPT.md`. It is intentionally implementation-oriented: every module should become independently testable engine code before UI work begins.

## Core Rules

1. Step 3 cannot run unless Step 2 validation passes.
2. Every confirmed batter in both lineups must be reviewed in Step 3.
3. Reports must preserve the required game, team, pool, YPI, and catcher boards.
4. Post-mortems must produce structured winner, loser, false-positive, and adjustment logs.
5. Formula weights must eventually be configurable so post-mortems can tune the engine without rewriting code.

## Step 1 Watchlist Intake

Step 1 collects candidate games, teams, batters, and matchup data before the hard validation gate.

### Required Inputs

- Game identifier and date
- Away team and home team
- Initial batter watchlist
- Probable or confirmed starting pitchers
- Available HR percentages or power indicators
- Available pitch-fit, weak-spot, or HR matchup data
- Notes from prior post-mortems

### Output

Step 1 should produce an intake object or CSV folder that can be passed into Step 2 validation. Step 1 is allowed to be incomplete, but anything missing must be visible before Step 2.

### Placeholder Decisions

- TODO: Define whether Step 1 accepts a single watchlist CSV or a folder of CSVs.
- TODO: Define minimum fields for a watchlist batter before enrichment.
- TODO: Define how prior post-mortem notes are linked to a batter or archetype.

## Step 2 Validation / No Shortcuts Gate

Step 2 is the hard gate. The engine must not allow Step 3 unless the game is complete enough for a full batter review.

### Required Inputs

- Game environment
- Umpire
- Starting pitchers
- Confirmed lineups
- Pitcher weak spots
- HR matchup files

### Validation Rules

- Both teams must have complete lineups.
- Every batter must have a team and lineup slot.
- Both starting pitchers must be present.
- Environment and umpire context must be present.
- Pitcher weak spots must be available.
- HR matchup data must be available.

### Failure Behavior

If validation fails, the engine must raise an error that lists every missing input. It should not return partial Step 3 rankings.

### Placeholder Decisions

- TODO: Define whether a complete lineup is exactly 9 batters or configurable for special cases.
- TODO: Define minimum accepted quality for weak-spot and HR matchup files.

## Step 3 Batter Review Format

Step 3 is the full batter review. Every batter in the confirmed lineup must be scored and displayed.

### Required Sections

- Game header
- Team vs pitcher table
- TAG/CPS summaries
- Gold pool
- Silver pool
- Bronze pool
- YPI board
- Catcher Power board

### Required Batter Fields

Each batter row should include:

- Batter name
- Team
- Lineup slot
- Bats / handedness when available
- Opposing pitcher
- HR percentage or power metric
- TAG component
- CPS component
- LSTM result
- PVS result
- Environment Score
- Umpire Score
- Special layers triggered
- Final score
- Tier or pool
- Notes

### Processing Order

1. Run Step 2 validation.
2. Calculate Environment Score and Umpire Score.
3. Calculate TAG and CPS for each team.
4. Score every batter with LSTM, PVS, YPI, Catcher Power, Veteran Bounce, Non-Superstar Core, and Chaos Cluster logic.
5. Apply guardrails such as Superstar Tax and lower-lineup penalties.
6. Build Gold, Silver, and Bronze pools.
7. Emit a confirmation that every batter was reviewed.

### Placeholder Decisions

- TODO: Define final Gold/Silver/Bronze thresholds.
- TODO: Define exact final-score formula after module weights are calibrated.

## Step 4 TAG/CPS Cluster Ranking

Step 4 ranks team clusters using TAG and CPS.

### Required Output

- Team
- Opposing pitcher
- TAG score and grade
- CPS score and grade
- Combined cluster score
- Core batters
- Cluster extension bats
- Notes explaining cluster strength or weakness

### Cluster Ranking Logic

TAG measures the team attack environment. CPS measures how usable and concentrated the team's HR candidates are. Step 4 combines them to identify the strongest team-level HR clusters.

### Placeholder Formula

```text
Cluster Ranking Score = (TAG * TAG_WEIGHT) + (CPS * CPS_WEIGHT) + special_context_adjustments
```

TODO: Tune `TAG_WEIGHT`, `CPS_WEIGHT`, and special context adjustments.

## Step 5 Slip Construction

Step 5 converts scored boards into candidate slip structures. It should not run until Step 3 and Step 4 outputs exist.

### Future Slip Types

- Core formula slip
- Non-superstar core slip
- YPI-focused slip
- Catcher Power slip
- Chaos cluster slip
- Ladder slip

### Required Output

Each slip candidate should include:

- Slip name
- Slip type
- Included batters
- Grade
- Rationale
- Module support summary

### Placeholder Decisions

- TODO: Define exact rules for slip size.
- TODO: Define when a slip is blocked by weak TAG/CPS context.
- TODO: Define ladder construction rules.

## Team Attack Grade (TAG)

TAG scores a team's overall HR attack quality against the opposing pitcher.

### Inputs

- Team batter HR percentages
- Top-half lineup power
- Number of viable HR bats
- Opposing pitcher projected HR, hits, walks, and tags
- Environment Score
- Umpire Score
- Park/weather context
- Prior post-mortem archetype carryover

### Output

- Numeric score from 0 to 100
- Letter grade
- Driver notes

### Placeholder Formula

```text
TAG = base_team_score
    + full_lineup_power_component
    + top_half_power_component
    + viable_hr_bat_component
    + pitcher_attackability_component
    + environment_component
    + umpire_component
    + postmortem_archetype_component
```

TODO: Tune all component weights and grade thresholds.

## Cluster Participation Score (CPS)

CPS measures whether a team's HR upside is concentrated in a playable cluster.

### Inputs

- Top HR bats by HR percentage
- Lineup positions of top HR bats
- Number of viable HR bats
- TAG support
- Environment support
- YPI or catcher participation
- Post-mortem archetype alignment

### Output

- Numeric score from 0 to 100
- Letter grade
- Core batter list
- Notes on cluster shape

### Placeholder Formula

```text
CPS = base_cluster_score
    + concentration_component
    + top_five_alignment_component
    + viable_bat_count_component
    + TAG_support_component
    + special_layer_component
    + environment_component
```

TODO: Define viable-bat threshold and lineup spacing rules.

## Lineup Slot Trend Multiplier (LSTM)

LSTM scores lineup position value. It replaces the older LPAS terminology with a trend/multiplier model.

### Baseline Slot Logic

- Slot 4: strongest baseline boost
- Slot 3: major boost
- Slot 1: major boost
- Slot 5: moderate boost
- Slot 2: smaller boost
- Slot 6: neutral
- Slot 7: boost only when TAG and CPS are A-level and cluster conditions are present
- Slots 8 and 9: penalty unless exceptional PVS, catcher, chaos, barrel, or environment support exists

### Output

- Slot score
- Multiplier
- Label
- Notes

### Placeholder Formula

```text
LSTM = slot_baseline
     + TAG_CPS_context_adjustment
     + plate_appearance_adjustment
     + lower_lineup_override_adjustment
```

TODO: Decide whether final scoring should use LSTM as additive score, multiplier, or both.

## Pitch Vulnerability Score (PVS)

PVS measures how well a batter's power profile collides with the opposing pitcher's weaknesses.

### Inputs

- Pitcher weak spots
- HR matchup records
- Batter pitch/path profile
- Pitch type
- Zone
- Exit velocity
- Launch angle
- Distance
- Pitcher projection data
- Handedness matchup when available

### Output

- Numeric score
- Label: none, light, strong, elite, or mismatch
- Matched pitch list
- Notes explaining collision quality

### Placeholder Formula

```text
PVS = weak_spot_match_component
    + HR_matchup_component
    + quality_of_contact_component
    + pitcher_projection_component
    + handedness_component
    - mismatch_penalty
```

TODO: Define exact pitch and zone matching rules.

## Environment Score

Environment Score measures park and weather impact on HR probability.

### Inputs

- Park HR factor
- Weather HR percentage
- Weather distance impact
- Temperature
- Wind speed
- Wind direction
- Humidity
- Roof status

### Output

- Numeric score
- Label: negative, neutral, positive, or extreme
- Component breakdown
- Notes

### Placeholder Formula

```text
Environment Score = park_component
                  + weather_hr_component
                  + distance_component
                  + wind_component
                  + temperature_component
                  + humidity_component
                  + roof_component
```

TODO: Add park-specific constants and wind direction mapping.

## Umpire Score

Umpire Score estimates how the umpire affects batter opportunity and run environment.

### Inputs

- Umpire zone type
- Called strike rate
- Accuracy
- Consistency
- Run lean

### Output

- Numeric score
- Label: hitter lean, neutral, or pitcher lean
- Notes

### Placeholder Formula

```text
Umpire Score = run_lean_component
             + zone_type_component
             + called_strike_component
             + accuracy_component
             + consistency_component
```

TODO: Calibrate against historical run and HR data.

## YPI / Young Power Index

YPI upgrades emerging bats whose power signals may not be fully priced into public perception.

### Inputs

- Young, rookie, prospect, small-sample, or YPI tags
- HR percentage
- Pitch-fit support
- Weak-spot fit
- LSTM support
- Post-mortem carryover

### Output

- YPI score or bonus
- YPI board inclusion flag
- Notes

### Placeholder Formula

```text
YPI = youth_profile_component
    + HR_signal_component
    + PVS_support_component
    + LSTM_support_component
    + postmortem_carryover_component
```

TODO: Define age, rookie, prospect, and sample-size thresholds.

## Catcher Power Layer

The Catcher Power Layer keeps catcher HR candidates visible because prior results showed catcher HRs can outperform ownership expectations.

### Inputs

- Catcher tag or position
- HR percentage
- PVS
- LSTM
- Environment Score
- TAG/CPS context
- Post-mortem catcher hit rate

### Output

- Catcher Power score or bonus
- Dedicated Catcher Power board
- Notes

### Placeholder Formula

```text
Catcher Power = catcher_visibility_bonus
              + catcher_power_profile_component
              + PVS_support_component
              + environment_support_component
              + postmortem_carryover_component
```

TODO: Define catcher-specific lower-lineup penalty relief.

## Veteran Bounce Rule

Veteran Bounce gives controlled credit to experienced power bats when the current context supports a rebound spot.

### Inputs

- Veteran, superstar, 5-tool, or power-threat tags
- LSTM
- PVS
- Environment Score
- Recent form if available

### Guardrails

Veteran Bounce must not become a name-value shortcut. Weak LSTM and weak PVS should limit or block the boost.

### Placeholder Formula

```text
Veteran Bounce = veteran_profile_component
               + LSTM_support_component
               + PVS_support_component
               + environment_support_component
               - unsupported_name_value_penalty
```

TODO: Define veteran eligibility and maximum boost.

## Non-Superstar Core Logic

Non-Superstar Core Logic prevents the board from being crowded out by famous names when lower-profile batters have stronger formula support.

### Inputs

- Superstar tag
- Final score
- PVS
- LSTM
- TAG/CPS support
- YPI, Catcher Power, Chaos, or Veteran Bounce flags
- Ownership or market signal when available

### Behavior

Superstars can still rank highly, but they should not receive an automatic override. Non-superstars with strong formula alignment should be eligible for Gold and Silver pools.

### Placeholder Formula

```text
Non-Superstar Core Score = final_score
                         + value_profile_bonus
                         + special_layer_bonus
                         - unsupported_superstar_penalty
```

TODO: Add ownership or market-value inputs when available.

## Chaos Cluster Rule

The Chaos Cluster Rule keeps low-ownership, lower-lineup, or small-sample bats visible when team context says the game can open up.

### Activation Conditions

- Strong TAG and CPS
- Positive Environment Score
- Batter is slot 6 through 9 with credible HR traits
- Batter has PVS, YPI, catcher, weak-spot, or post-mortem support

### Guardrails

Chaos bats should not outrank core bats unless they have meaningful PVS, special-layer, or environment support.

### Placeholder Formula

```text
Chaos Bonus = cluster_context_bonus
            + low_ownership_profile_bonus
            + special_layer_bonus
            + PVS_support_bonus
            - weak_profile_penalty
```

TODO: Define maximum chaos bonus and required activation thresholds.

## Pitcher Weak-Spot Collision

Pitcher Weak-Spot Collision is the specific matching layer inside PVS that compares batter strengths to pitcher vulnerabilities.

### Inputs

- Pitcher weak-spot pitch type
- Pitcher weak-spot zone
- Batter pitch/path profile
- HR matchup pitch type
- Exit velocity, launch angle, and distance where available

### Output

- Collision score
- Matched pitch/zone list
- Collision label
- Notes

### Placeholder Formula

```text
Weak-Spot Collision = pitch_type_match
                    + zone_match
                    + batter_path_match
                    + quality_contact_match
                    - unsupported_match_penalty
```

TODO: Define batter path data model and matching rules.

## Winner Log

The Winner Log records successful calls from the formula.

### Required Fields

- Date
- Game
- Batter
- Team
- Opposing pitcher
- Final score
- Pool or board
- TAG/CPS grades
- Triggered modules
- HR pitch when available
- Notes

### Purpose

Winners should identify which formula modules correctly surfaced the batter.

## Loser Log

The Loser Log records formula-backed calls that did not hit.

### Required Fields

- Date
- Game
- Batter
- Team
- Opposing pitcher
- Final score
- Pool or board
- TAG/CPS grades
- Triggered modules
- Notes

### Purpose

Losers should identify whether the miss came from weak PVS, overboosted environment, unsupported name value, poor cluster read, or normal variance.

## False Positive Log

False positives are high-confidence calls that had weak hidden support or repeated failure patterns.

### Required Fields

- Date
- Batter
- Team
- False-positive reason
- Overweighted modules
- Suggested adjustment

### Purpose

This log protects the formula from repeating bad patterns.

## Post-Mortem Adjustment Log

The Adjustment Log turns winners, losers, and false positives into tuning recommendations.

### Review Dimensions

- TAG hit rate
- CPS hit rate
- LSTM hit rate
- PVS hit rate
- Environment Score hit rate
- Umpire Score hit rate
- YPI hit rate
- Catcher Power hit rate
- Veteran Bounce hit rate
- Chaos Cluster hit rate
- Superstar false positives
- Almost-made-it winners

### Placeholder Formula

```text
Adjustment Recommendation = module_hit_rate_delta
                          + false_positive_pattern
                          + missed_winner_pattern
                          + sample_size_confidence
```

TODO: Define sample-size thresholds before automatic weight changes are allowed.
TODO: Define which adjustments require manual approval.

## Implementation Guidance

- Use strongly typed dataclasses for module inputs and outputs.
- Keep scoring modules independent and unit-testable.
- Keep Step 2 validation as the hard no-shortcuts gate.
- Do not build UI until the engine, reports, and logs are reliable.
- Keep exact weights configurable once post-mortem learning begins.
