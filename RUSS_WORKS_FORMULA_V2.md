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

Step 1 collects candidate games, teams, batters, and matchup data before the hard validation gate. Step 1 is an intake and enrichment stage, not a ranking stage.

### Required Inputs

- Game identifier and date
- Away team and home team
- Initial batter watchlist
- Probable or confirmed starting pitchers
- Available HR percentages or power indicators
- Available pitch-fit, weak-spot, or HR matchup data
- Notes from prior post-mortems

### Intake Output

Step 1 should produce an intake object or CSV folder that can be passed into Step 2 validation. The intake can be incomplete, but every missing field must be visible in validation output.

### Watchlist Handling

- Watchlist batters are candidates only.
- Watchlist presence does not guarantee Step 3 pool inclusion.
- Batters not on the original watchlist must still be reviewed if they appear in the confirmed lineup.
- Prior post-mortem notes can tag an archetype, such as young power, catcher power, weak-spot fit, or unsupported superstar.

### Remaining Placeholders

- TODO: Define whether Step 1 accepts a single watchlist CSV or a folder of CSVs.
- TODO: Define minimum fields for a watchlist batter before enrichment.
- TODO: Define how prior post-mortem notes are linked to a batter, team, pitcher, or archetype.

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

- Both teams must have complete confirmed lineups.
- Every batter must have a team, lineup slot, and confirmed status.
- Both starting pitchers must be present.
- Environment and umpire context must be present.
- Pitcher weak spots must be available.
- HR matchup data must be available.

### Failure Behavior

If validation fails, the engine must raise an error that lists every missing input. It should not return partial Step 3 rankings.

### Remaining Placeholders

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

### Pool Threshold Guidance

- Gold pool: clear formula-backed targets with strong total score, strong PVS or elite cluster context, and no major guardrail failure.
- Silver pool: playable targets with one or two strong module supports but incomplete elite alignment.
- Bronze pool: watchlist, chaos, or speculative targets that remain visible but require caution.
- No pool: reviewed batters whose score or context does not justify inclusion.

### Remaining Placeholders

- TODO: Define exact numeric Gold/Silver/Bronze thresholds after historical calibration.
- TODO: Define exact final-score formula after module weights are calibrated.

## Step 4 TAG/CPS Cluster Ranking

Step 4 ranks team clusters using TAG and CPS. It answers which team environments deserve the most attention before Step 5 converts batter pools into slip structures.

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

### CPS Influence on Step 4 Rankings

- High TAG plus high CPS should rank as the strongest team cluster profile.
- High TAG plus low CPS means the offense is interesting, but HR production may be spread or hard to isolate.
- Low TAG plus high CPS means the team has a concentrated pocket, but the overall environment may cap upside.
- Low TAG plus low CPS should usually stay below the main Step 5 construction line.

### Working Formula

```text
Cluster Ranking Score = (TAG * TAG_WEIGHT) + (CPS * CPS_WEIGHT) + special_context_adjustments
```

Recommended starting weights:

- `TAG_WEIGHT`: 0.45
- `CPS_WEIGHT`: 0.55
- `special_context_adjustments`: controlled bonuses for YPI, catcher power, chaos, or post-mortem archetypes

TODO: Tune weights after post-mortem sample size is large enough.

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

### Value-Based Slip Construction

Step 5 should not simply take the highest name-value batters. It should preserve formula reasons:

- Core slips should lean on Gold pool batters with strong TAG/CPS and PVS support.
- Non-superstar slips should surface lower-profile bats with strong formula alignment.
- YPI slips should keep young power profiles grouped and visible.
- Catcher slips should only include catchers with meaningful power, PVS, or context support.
- Chaos slips should remain capped and clearly labeled as higher variance.

### Remaining Placeholders

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

### Grade Definitions

- A+: elite team attack. Multiple top-half HR threats, strong pitcher vulnerability, favorable run/HR environment, and clear cluster support.
- A: strong team attack. At least one high-end HR pocket plus meaningful team depth or pitcher vulnerability.
- B: viable team attack. Playable context with some HR indicators, but not enough to dominate the slate by itself.
- C: thin team attack. One-off bats may be viable, but team-level support is weak or uneven.
- D: avoid as a team cluster. Bats can still be reviewed, but the team context should not drive slip construction.

### Offensive Cluster Indicators

TAG should rise when the offense shows several of these signals:

- Multiple batters with above-threshold HR percentage.
- At least two strong HR profiles in lineup slots 1 through 5.
- A power pocket around slots 3, 4, and 5.
- Lower-lineup extension from slot 6 or 7 that is supported by CPS.
- Strong matchup against a pitcher with HR, contact, or walk vulnerability.
- Positive Environment Score or hitter-leaning Umpire Score.

### Team HR Momentum

Team HR momentum captures whether the team's recent power profile supports an aggressive read. Until live recent-form data is modeled, it should be represented by tags or post-mortem archetype carryover.

Momentum indicators include:

- Recent team HR production.
- Multiple batters carrying hot power tags.
- Prior post-mortems showing the team or archetype repeatedly reaching the board.
- Strong weather and park context aligning with existing power bats.

TODO: Define exact recent-game window and whether momentum is team-level, batter-level, or both.

### Run-Production Concentration

TAG should distinguish concentrated offense from empty depth. Run-production concentration is strongest when the best HR profiles also sit in RBI or plate-appearance slots.

High concentration examples:

- Power bats in slots 1, 3, 4, and 5.
- A 3-4-5 pocket with all three batters carrying HR viability.
- A leadoff power bat followed by high-contact or power support.

Low concentration examples:

- One elite name surrounded by weak HR profiles.
- Most HR signals buried in slots 8 and 9 without PVS or environment relief.
- Team power spread so evenly that no clear cluster can be built.

### Working Formula

```text
TAG = base_team_score
    + full_lineup_power_component
    + top_half_power_component
    + viable_hr_bat_component
    + pitcher_attackability_component
    + environment_component
    + umpire_component
    + team_hr_momentum_component
    + run_production_concentration_component
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

### CPS Grading System

- A+: elite cluster. Several strong HR profiles are close enough in lineup order and context to drive Step 4 and Step 5.
- A: strong cluster. The team has a clear playable pocket, usually supported by TAG.
- B: viable cluster. Enough power exists to keep the team in play, but one or more support signals are missing.
- C: weak or scattered cluster. One-off batter plays may remain, but the team cluster is not strong.
- D: no reliable cluster. Power is too thin, too unsupported, or too disconnected.

### Concentrated vs Distributed Power

Concentrated power means the strongest HR profiles are grouped in a way that helps ranking and slip construction. Distributed power means viable bats exist, but the offense lacks a clear construction path.

Concentrated power indicators:

- Three or four top HR profiles inside a tight lineup span.
- Multiple top HR profiles in slots 1 through 5.
- A strong 3-4-5 pocket.
- A slot 6 or 7 extension supported by A-level TAG and CPS.

Distributed power indicators:

- Top HR profiles scattered across slots 1, 5, 8, and 9.
- One elite top-half bat plus several low-context speculative bats.
- Lower-lineup power without PVS, catcher, chaos, or environment support.

### Relationship Between CPS and TAG

TAG describes team attack quality. CPS describes whether that attack can be organized into a playable cluster.

- TAG can be high while CPS is low if the whole team environment is strong but no clear pocket exists.
- CPS can be high while TAG is middling if a small group of batters has strong HR viability in a lower-scoring context.
- Step 4 should favor teams where TAG and CPS confirm each other.
- Step 5 should treat TAG/CPS disagreement as a risk label, not an automatic rejection.

### CPS Influence on Step 4 Rankings

CPS is the sorting pressure that prevents Step 4 from becoming a generic team-strength board. Strong CPS should elevate teams with actionable HR clusters, especially when TAG is also strong.

Step 4 interpretation:

- A/A or A+/A CPS-TAG pairing: primary cluster candidate.
- A CPS with B TAG: targeted pocket candidate.
- B CPS with A TAG: team is playable, but slips need tighter batter filtering.
- C or D CPS: avoid team stacks unless individual PVS is exceptional.

### Working Formula

```text
CPS = base_cluster_score
    + concentration_component
    + top_five_alignment_component
    + viable_bat_count_component
    + TAG_support_component
    + special_layer_component
    + environment_component
```

TODO: Define exact viable-bat threshold and lineup spacing rules.

## Lineup Slot Trend Multiplier (LSTM)

LSTM scores lineup position value. It replaces the older LPAS terminology with a trend/multiplier model.

### Slot-Specific Rules

#### #1 Hitter Bonus

The #1 hitter gets a plate-appearance and tone-setting bonus. This slot is strongest when the batter has real HR power, not only speed or contact.

- Baseline: positive.
- Upgrade when HR percentage is strong or PVS is strong.
- Downgrade when the batter is a pure table-setter without power indicators.

#### #2 Hitter Bonus

The #2 hitter gets a smaller bonus than #1, #3, or #4. The slot is useful because it combines plate appearances with lineup protection.

- Baseline: mildly positive.
- Upgrade when the batter has PVS or YPI support.
- Avoid overboosting low-power contact bats.

#### #3 Hitter Bonus

The #3 hitter gets a major bonus because the slot usually combines plate appearances, run production, and lineup trust.

- Baseline: strong positive.
- Upgrade when TAG and CPS are also strong.
- Strong PVS can push this slot into core consideration.

#### #4 Hitter Bonus

The #4 hitter receives the strongest baseline boost. This is the primary power and run-production slot.

- Baseline: strongest positive.
- Upgrade when PVS, TAG, and CPS all align.
- This slot should still be penalized if the batter lacks power indicators.

#### #5 Hitter Bonus

The #5 hitter receives a moderate power-slot bonus. This slot can be especially useful when the 3-4-5 pocket is live.

- Baseline: moderate positive.
- Upgrade when adjacent power bats create a cluster.
- Downgrade when team TAG/CPS context is weak.

#### Conditional #7 Hitter Bonus

The #7 hitter is normally not a premium slot, but V2 keeps the slot alive when the team context is strong.

Activation conditions:

- TAG is A-level or better.
- CPS is A-level or better.
- The batter has PVS, YPI, catcher, chaos, or environment support.
- The batter is part of a real offensive cluster extension.

#### #8 and #9 Penalties

Slots 8 and 9 receive baseline penalties because they generally have fewer plate appearances and weaker run-production context.

Penalty relief can occur when:

- PVS is strong or elite.
- Catcher Power Layer applies.
- Chaos Cluster Rule applies.
- Environment Score is strongly positive.
- Post-mortem history supports the archetype.

### Output

- Slot score
- Multiplier
- Label
- Notes

### Working Formula

```text
LSTM = slot_baseline
     + TAG_CPS_context_adjustment
     + plate_appearance_adjustment
     + lower_lineup_override_adjustment
```

TODO: Decide whether final scoring should use LSTM as additive score, multiplier, or both.

## Pitch Vulnerability Score (PVS)

PVS measures how well a batter's power profile collides with the opposing pitcher's weaknesses. Pitcher Weak-Spot Collision is a subcomponent of PVS and should not be counted a second time outside PVS.

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

### Working Formula

```text
PVS = weak_spot_collision_component
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

### Definition

A Non-Superstar Core bat is a player without superstar/name-value dependency who earns pool or slip consideration through formula alignment. The player may be young, overlooked, lower-owned, or simply less public-facing, but the defining feature is that the formula supports the play without relying on reputation.

### Identification Criteria

A batter can qualify when several of these are true:

- No superstar tag or name-value override is required.
- Final score is Gold or strong Silver level.
- PVS is strong or elite.
- LSTM is neutral or positive, or lower-lineup penalty relief applies.
- Team TAG/CPS context is supportive.
- YPI, Catcher Power, Chaos Cluster, or Veteran Bounce adds a legitimate secondary layer.
- Market or ownership signal, when available, suggests the player is not obvious public chalk.

### Post-Mortem Justification

Post-mortems should track Non-Superstar Core performance because these bats can reveal formula edges. The review should ask:

- Did the batter win because of PVS, LSTM, TAG/CPS, or special-layer support?
- Was the player omitted from obvious public builds but supported by the formula?
- Did a similar archetype appear in previous winners or near misses?
- Did the formula over-promote a value bat without enough real collision?

### Value-Based Slip Construction

Non-Superstar Core slips should be built from formula alignment, not from contrarianism alone.

Slip construction rules:

- Require strong module support, usually PVS plus TAG/CPS or LSTM.
- Prefer players with clear notes explaining why they are not just speculative.
- Avoid stacking multiple weak-context value bats in the same slip.
- Use post-mortem results to identify which value archetypes deserve repeat inclusion.

### Working Formula

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

Pitcher Weak-Spot Collision is the specific matching layer inside PVS that compares batter strengths to pitcher vulnerabilities. It should be implemented as a PVS component, not as a separate additive module outside PVS.

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

### Winner Log Process

1. Import official result data.
2. Match each HR winner to the original Step 3 board.
3. Record the batter's pool, score, and triggered modules.
4. Identify whether the winning signal came from TAG, CPS, LSTM, PVS, YPI, catcher, veteran, chaos, or non-superstar logic.
5. Mark whether the winner was core, secondary, chaos, or missed by the formula.
6. Send missed winners to the adjustment review queue.

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

### Loser Log Process

1. Import all Step 3 pool batters who did not win.
2. Preserve their original score, tier, and module notes.
3. Classify the miss as normal variance, weak PVS, overboosted environment, weak TAG/CPS, unsupported name value, or bad chaos extension.
4. Flag repeated miss patterns for threshold adjustment.
5. Keep normal-variance misses separate from formula-error misses.

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

### Threshold Adjustment Process

1. Group outcomes by module and archetype.
2. Compare winner frequency against loser and false-positive frequency.
3. Identify repeated misses from the same threshold, such as too-low PVS minimums or too-generous lower-lineup relief.
4. Propose threshold changes as recommendations, not automatic rewrites.
5. Require enough sample size before changing core thresholds.
6. Record every accepted or rejected threshold change in the Adjustment Log.

### Formula Calibration Process

Calibration should be deliberate and reversible.

1. Start with module-level hit rates.
2. Separate signal misses from normal baseball variance.
3. Compare almost-made-it winners against current thresholds.
4. Compare false positives against the modules that overpromoted them.
5. Adjust one family of weights or thresholds at a time.
6. Keep default weights in configuration.
7. Preserve a dated note explaining why each calibration happened.

### Working Adjustment Formula

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
