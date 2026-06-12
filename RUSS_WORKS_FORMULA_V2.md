# Russ-Works Formula V2 Specification

## Purpose

Russ-Works Formula V2 defines the engine rules for a repeatable MLB home-run analysis workflow. The goal is to prevent shortcuts, score every confirmed batter, surface undervalued power profiles, and produce standardized Step 3 through Step 5 reports plus post-mortem learning logs.

This document expands the original `RUSS_WORKS_SPEC.md` into implementation-ready modules. Where exact coefficients still require historical calibration, this spec leaves explicit placeholders instead of inventing final weights.

## Core Principles

1. Step 3 cannot run unless Step 2 validation passes.
2. Every batter in both confirmed lineups must be reviewed and scored.
3. Team context matters before individual picks are promoted.
4. Name value alone is not enough to override weak formula support.
5. Young power, catcher power, cluster beneficiaries, and low-ownership profiles must be visible in the report.
6. Post-mortems must feed future adjustments through structured logs.

## Required Step 2 Inputs

The engine must block Step 3 unless all of these inputs are present:

- Game environment
- Umpire
- Starting pitchers
- Confirmed lineups
- Pitcher weak spots
- HR matchup data

Failure mode: raise a validation error that lists every missing input.

## Team Attack Grade (TAG)

TAG measures the offensive attack quality of a team against the opposing pitcher in the current game context.

### Inputs

- Team batter HR percentages
- Top-half lineup strength, especially slots 1 through 5
- Number of viable HR bats
- Opposing pitcher HR vulnerability
- Park and weather context
- Umpire run/zone lean
- Post-mortem archetype carryover

### Output

TAG produces:

- Numeric score from 0 to 100
- Letter grade: A+, A, A-, B+, B, B-, C, D
- Notes explaining the strongest drivers

### Intended Behavior

A high TAG team should have multiple credible HR paths, favorable environment or pitcher context, and at least one strong concentration point in the lineup. TAG should not be boosted only because one superstar exists.

### Placeholder Formula

```text
TAG = base_team_attack
    + top_half_power_component
    + viable_hr_bat_component
    + pitcher_attackability_component
    + environment_component
    + umpire_component
    + postmortem_archetype_component
```

TODO: Calibrate final coefficients for each component using post-mortem history.

## Cluster Participation Score (CPS)

CPS measures whether a team's HR upside is concentrated in a usable cluster or spread across disconnected bats.

### Inputs

- HR concentration among the top four or five HR profiles
- Lineup positions of the strongest HR bats
- Number of viable HR bats
- TAG score
- Young power and catcher power participation
- Recent post-mortem archetype alignment
- Environment boost or penalty

### Output

CPS produces:

- Numeric score from 0 to 100
- Letter grade
- Cluster core list of batters
- Notes describing concentration or spread

### Intended Behavior

A high CPS team should have several playable bats close together in lineup order or profile type. CPS should reward clusters such as top-half power pockets, young power clusters, catcher/chaos extensions, and teams where slots 6 or 7 are viable because the broader team context is strong.

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

TODO: Define exact threshold for viable HR bat and exact cluster spacing rules.

## Lineup Slot Trend Multiplier (LSTM)

LSTM replaces the older LPAS naming with a clearer multiplier-style model. It captures how lineup position changes the reliability of a batter's HR profile.

### Baseline Slot Guidance

- Slot 4: strongest baseline boost
- Slot 3: major boost
- Slot 1: major plate-appearance and tone-setter boost
- Slot 5: moderate boost
- Slot 2: smaller boost
- Slot 6: neutral
- Slot 7: conditional boost only when TAG and CPS are A-level and cluster conditions are present
- Slots 8 and 9: penalty unless there is exceptional collision, barrel, catcher, chaos, or environment support

### Output

LSTM produces:

- Numeric multiplier or additive score
- Slot rationale
- Conditional override flag for lower-lineup bats

### Placeholder Formula

```text
LSTM = slot_baseline
     + TAG_CPS_context_adjustment
     + plate_appearance_adjustment
     + lower_lineup_override_adjustment
```

TODO: Decide whether implementation should use an additive score, a multiplier, or both.

## Pitch Vulnerability Score (PVS)

PVS measures the collision between batter strengths and pitcher weaknesses.

### Inputs

- Pitcher weak spots
- Batter pitch/path profile
- HR matchup records
- Pitch type, zone, exit velocity, launch angle, and distance when available
- Pitcher projected HR, hits, walks, and tags
- Batter handedness versus pitcher handedness

### Output

PVS produces:

- Numeric score
- Collision label: none, light, strong, elite
- Matched weak spots
- Notes for report explanation

### Intended Behavior

PVS should promote batters whose power path directly attacks a known pitcher weakness. It should penalize weak or missing pitch fit when a batter's case relies only on name value.

### Placeholder Formula

```text
PVS = weak_spot_match_component
    + HR_matchup_component
    + quality_of_contact_component
    + pitcher_projection_component
    + handedness_component
    - mismatch_penalty
```

TODO: Define exact matching rules for pitch, zone, and batter path profile.

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

Environment Score produces:

- Numeric score
- Environment label: negative, neutral, positive, extreme
- Notes for park/weather drivers

### Intended Behavior

The module should boost games with meaningful HR weather, wind out, warm temperature, favorable park factors, or added carry. It should penalize closed roofs, suppressive wind, or weak carry conditions.

### Placeholder Formula

```text
Environment Score = park_component
                  + weather_hr_component
                  + distance_component
                  + wind_component
                  + temperature_component
                  + roof_component
```

TODO: Define park-specific factors and directional wind mapping.

## Umpire Score

Umpire Score captures how the umpire may influence run environment and batter opportunity.

### Inputs

- Umpire zone type
- Called strike rate
- Accuracy
- Consistency
- Run lean
- Walk friendliness or strike-zone strictness

### Output

Umpire Score produces:

- Numeric score
- Umpire label: hitter lean, neutral, pitcher lean
- Notes for zone/run behavior

### Intended Behavior

A hitter-friendly umpire can slightly lift TAG, CPS, and individual batter context. A pitcher-friendly umpire should slightly suppress borderline bats, especially those without strong PVS or LSTM support.

### Placeholder Formula

```text
Umpire Score = run_lean_component
             + zone_type_component
             + called_strike_component
             + consistency_component
```

TODO: Calibrate umpire score ranges against historical HR and run data.

## Chaos Cluster Rule

The Chaos Cluster Rule keeps low-ownership or lower-lineup bats visible when team context says the game can break open.

### Activation Conditions

Chaos consideration can activate when:

- TAG and CPS are both strong
- Environment Score is positive
- Batter is in slot 6 through 9 with credible HR traits
- Batter has catcher, YPI, weak-spot, or pitch-collision support
- Post-mortems show similar profiles winning or nearly winning

### Guardrails

Chaos bats should not outrank strong core bats unless they also have meaningful PVS, environment, or special-layer support.

### Placeholder Formula

```text
Chaos Bonus = cluster_context_bonus
            + low_ownership_profile_bonus
            + special_layer_bonus
            + PVS_support_bonus
            - weak_profile_penalty
```

TODO: Define the maximum chaos boost so the layer stays controlled.

## Veteran Bounce Rule

Veteran Bounce gives a controlled upgrade to veteran power bats when the formula supports a rebound spot.

### Activation Conditions

- Batter has veteran, power, superstar, or long-term production profile
- LSTM is neutral or positive
- PVS is strong enough to justify the boost
- Environment or team context is not suppressive

### Guardrails

Veteran Bounce should not become a name-value shortcut. If PVS and LSTM are weak, the boost should be small or blocked.

### Placeholder Formula

```text
Veteran Bounce = veteran_profile_component
               + LSTM_support_component
               + PVS_support_component
               + environment_support_component
               - name_value_tax
```

TODO: Define veteran qualification tags and age/experience criteria if data becomes available.

## Catcher Power Layer

The Catcher Power Layer explicitly surfaces catcher HR profiles because prior post-mortems showed catcher HRs outperforming ownership expectations.

### Inputs

- Catcher tag or position field
- HR percentage
- LSTM
- PVS
- Environment Score
- TAG/CPS context
- Post-mortem catcher hit rate

### Output

The report must include a dedicated Catcher Power board.

### Intended Behavior

Catchers should be promoted into visibility when they have legitimate power support, even if they are lower in the lineup. The layer should not blindly boost all catchers.

### Placeholder Formula

```text
Catcher Power = catcher_visibility_bonus
              + catcher_HR_profile_component
              + PVS_support_component
              + environment_support_component
              + postmortem_carryover_component
```

TODO: Define catcher-specific thresholds for HR percentage and lineup penalty relief.

## Non-Superstar Core Logic

Non-Superstar Core Logic prevents the slate from being dominated by famous names when value bats have stronger formula alignment.

### Inputs

- Superstar tag
- Final score
- PVS
- LSTM
- TAG/CPS support
- YPI, Catcher Power, Chaos, or Veteran Bounce flags
- Ownership or market signal when available

### Intended Behavior

Superstars can still grade highly, but they should not receive an automatic override. Non-superstars with strong PVS, LSTM, TAG/CPS, and special-layer support should be eligible for Gold/Silver pool visibility.

### Placeholder Formula

```text
Non-Superstar Core Score = final_score
                         + value_profile_bonus
                         + special_layer_bonus
                         - unsupported_superstar_penalty
```

TODO: Add ownership and market-value inputs when available.

## Step 3 Workflow

Step 3 is the full batter review.

### Preconditions

- Step 2 validation passes
- Both lineups are confirmed
- Every team has a complete lineup
- Pitcher weak spots and HR matchup data are available

### Required Output Sections

- Game header
- Team vs pitcher table
- TAG/CPS summaries
- Gold/Silver/Bronze pools
- YPI board
- Catcher Power board

### Processing Sequence

1. Validate Step 2 inputs.
2. Calculate Environment Score and Umpire Score.
3. Calculate TAG and CPS for each team.
4. Score every batter using LSTM, PVS, special layers, and team context.
5. Apply Superstar Tax, Non-Superstar Core Logic, Chaos Cluster Rule, Veteran Bounce, and Catcher Power Layer.
6. Build ranked Gold, Silver, and Bronze pools.
7. Emit explicit confirmation that every batter was reviewed.

## Step 4 Workflow

Step 4 builds TAG/CPS cluster context.

### Required Output

- Team TAG score and grade
- Team CPS score and grade
- Cluster score
- Core batters
- Cluster notes

### Processing Sequence

1. Read all Step 3 team-level scores.
2. Identify core HR clusters by team.
3. Identify cluster extensions such as slot 6/7 bats, catcher power, and YPI bats.
4. Mark teams with strong stack potential or weak cluster support.
5. Preserve results for Step 5 slip construction.

## Step 5 Workflow

Step 5 converts scored boards into candidate slip structures. Slip generation is not part of Phase 1 implementation, but the formula spec reserves the workflow.

### Required Future Output

- Core slip candidates
- Value or non-superstar slips
- YPI-focused slips
- Catcher or chaos slips
- Ladder-style variants
- Rationale for each slip

### Placeholder Workflow

```text
Step 5 candidates = ranked_batter_pools
                  + TAG_CPS_cluster_context
                  + special_layer_boards
                  + postmortem_adjustments
```

TODO: Define final slip construction rules after Phase 1 scoring modules are stable.

## Post-Mortem Workflow

Post-mortem learning turns results into structured logs and future adjustment inputs.

### Required Output Sections

- Winners Log
- Losers Log
- False Positive Log
- Adjustment Log

### Review Dimensions

- YPI hit rate
- Catcher hit rate
- TAG/CPS hit rate
- LSTM hit rate
- PVS or weak-spot hit rate
- Superstar false positives
- Almost-made-it winners
- Chaos cluster outcomes
- Veteran Bounce outcomes

### Processing Sequence

1. Load final game results.
2. Compare actual HR outcomes to Step 3 scores and pools.
3. Classify entries as winners, losers, false positives, or near misses.
4. Identify which modules helped or hurt each call.
5. Write structured logs.
6. Produce adjustment recommendations.
7. Feed approved adjustments into configurable formula weights.

### Placeholder Adjustment Logic

```text
Adjustment Recommendation = module_hit_rate_delta
                          + false_positive_pattern
                          + missed_winner_pattern
                          + sample_size_confidence
```

TODO: Define minimum sample sizes and confidence thresholds before automatic weight changes are allowed.

## Implementation Notes

- Use strongly typed dataclasses for each module result.
- Keep formula modules independent enough to unit test separately.
- Preserve Step 2 validation as the hard gate before Step 3.
- Do not build UI until engine correctness, outputs, and logs are stable.
- Keep all weights configurable once post-mortem learning begins.
