# Trading Hypotheses

## 1. Scope

R9 converts the surviving `R8` edge candidates into a small set of formal trading hypotheses.

This phase stays deliberately narrow:

- no new candidate discovery
- no strategy implementation
- no parameter widening

Inputs:

- `docs/research/statistical_reality_checks.md`
- `docs/research/edge_candidate_detection.md`
- `outputs/diagnostics/statistical_reality_checks/`
- `outputs/diagnostics/edge_candidates/`
- `outputs/diagnostics/hypotheses/hypothesis_catalog.csv`
- `outputs/diagnostics/hypotheses/hypothesis_priority_summary.csv`

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

## 2. Why The Candidate Set Is Narrow

R7 reduced the reset tree to one credible structural pattern:

- `expanded_contextual_breaches_h4`

R8 then narrowed that region into five edge candidates:

- `ecb_01`
- `ecb_02`
- `ecb_03`
- `ecb_04`
- `ecb_05`

Those candidates are not equal-priority. The main research path remains:

- pooled downside continuation in strongly expanded London and early-New-York contexts

The secondary path remains:

- `USDJPY`-specific upside continuation

The early-New-York upside sweep candidate remains only a side case.

## 3. Hypothesis Families

### Family H1: Expanded downside structural continuation in London / early New York

Source candidates:

- `ecb_01`
- `ecb_02`
- `ecb_04`

Priority:

- `Tier 1`

This is the main path because it is the cleanest pooled continuation family left after R7 and R8.

#### H1A

- `hypothesis_id`: `H1A`
- `priority_tier`: `Tier 1`
- `source_candidate_id`: `ecb_01|ecb_02`
- `pair_scope`: `ALL`
- `session_context`: `London`
- `structural_condition`: strongly expanded London session with downside structural breach, specifically `breakout_low` or `sweep_low`
- `regime_condition`: `range_regime == strongly_expanded`; volatility is not fixed, but the effect should remain strongest outside low-information compressed contexts
- `expected_directional_effect`: downside continuation in breach direction
- `expected_holding_horizon`: `h4`

Formal hypothesis statement:

When London is already in a strongly expanded state and price produces a downside structural breach, subsequent `h4` aligned returns should continue in the breach direction more often than the expanded-breach baseline across the pooled pairs.

Market intuition:

In already-expanded London conditions, a downside structural breach is more likely to reflect genuine directional repricing and order-flow imbalance than a simple stop-run. The R8 payoff profile suggests that this continuation is not purely one-bar noise and can persist across the next few bars.

Measurable predictions:

- aligned `h4` mean return should remain positive
- continuation fraction should remain materially above the base-region `0.5497`
- the effect should remain positive at `h1`, `h2`, `h4`, and `h8`
- pooled support should not rely on only one pair

Invalidation criteria:

- aligned `h4` mean return falls back toward zero or negative
- continuation fraction converges toward the base-region average
- one pair becomes strongly contradictory while pooled results stay positive only by aggregation
- the effect survives only for one exact breach subtype and collapses under minimal structural grouping

Risks / confounders:

- pooled downside continuation may still be partly carried by `GBPUSD`
- downside aligned effects can look stronger than raw-return fractions suggest, so sign handling must stay explicit
- later strategy design could fail if trade timing cannot capture the structural continuation cleanly

Notes for later strategy design:

- R10 should test immediate continuation versus one-bar confirmation
- first experiment set should compare `breakout_low` and `sweep_low` under the same structural filter rather than splitting the family too early

#### H1B

- `hypothesis_id`: `H1B`
- `priority_tier`: `Tier 1`
- `source_candidate_id`: `ecb_04`
- `pair_scope`: `ALL`
- `session_context`: `early New York`
- `structural_condition`: strongly expanded early-New-York `sweep_low`
- `regime_condition`: `range_regime == strongly_expanded`
- `expected_directional_effect`: downside continuation in breach direction
- `expected_holding_horizon`: `h4`

Formal hypothesis statement:

When early New York opens inside a strongly expanded context and prints a downside sweep, the next `h4` aligned return should continue downward more often than the expanded-breach baseline.

Market intuition:

Early New York appears to inherit directional state from the earlier expansion regime rather than automatically reversing it. In that context, some downside sweeps may be failed reclaims rather than exhaustion events, leading to continued directional movement.

Measurable predictions:

- aligned `h4` mean return should remain positive
- continuation fraction should stay above the base-region continuation fraction
- aligned outcomes should remain positive through `h1`, `h2`, `h4`, and `h8`
- the effect should remain visible across at least two pairs if pooled

Invalidation criteria:

- early New York sweeps revert toward neutrality once retested on a strategy-style event stream
- continuation fraction falls below the London downside family
- the edge proves to be mostly magnitude without useful directional asymmetry
- pair pooling hides strong disagreement between `EURUSD` and `GBPUSD`

Risks / confounders:

- early New York is a narrower context than London and may be more execution-sensitive later
- some of the effect may depend on state inherited from London, not on the sweep itself

Notes for later strategy design:

- R10 should compare pure early-New-York event entry against a “carry from London expansion” framing
- this branch should remain in the same family as H1A rather than becoming a separate strategy family immediately

### Family H2: USDJPY upside continuation after expanded New York upside breach

Source candidate:

- `ecb_05`

Priority:

- `Tier 2`

This remains secondary because it is pair-specific and should not displace the pooled downside track.

#### H2

- `hypothesis_id`: `H2`
- `priority_tier`: `Tier 2`
- `source_candidate_id`: `ecb_05`
- `pair_scope`: `USDJPY`
- `session_context`: `New York`
- `structural_condition`: strongly expanded `breakout_high`
- `regime_condition`: `range_regime == strongly_expanded`
- `expected_directional_effect`: upside continuation
- `expected_holding_horizon`: `h4`

Formal hypothesis statement:

In `USDJPY`, when New York is already strongly expanded and price breaks above structural highs, subsequent `h4` returns should continue upward more often than the pooled expanded-breach baseline.

Market intuition:

Across R2 through R8, `USDJPY` repeatedly carried directional state more cleanly than `EURUSD` and `GBPUSD`. The R8 candidate suggests that upside structural breaks in strongly expanded New York conditions may reflect persistent directional state rather than noisy breach behavior.

Measurable predictions:

- aligned `h4` mean return should remain positive in `USDJPY`
- continuation fraction should remain above `USDJPY`’s own expanded-breach baseline
- the effect should stay positive through nearby horizons even if smaller than the main pooled downside family
- the effect should remain stronger in `USDJPY` than when naively pooled into the European pairs

Invalidation criteria:

- the effect disappears once re-tested with small timing or structural adjustments
- `USDJPY` no longer outperforms pooled or European-pair counterparts under the same condition
- the horizon profile turns positive only at one isolated point
- later strategy experiments show the effect is too small after simple friction

Risks / confounders:

- this is pair-specific and therefore more vulnerable to overfitting
- the raw magnitude is smaller than the main Tier 1 candidates
- `USDJPY` may require different execution assumptions later

Notes for later strategy design:

- R10 should keep this branch separate from pooled experiments
- the first experiment should stay close to the exact R8 condition before trying any extra context

### Family H3: Early New York upside sweep side case

Source candidate:

- `ecb_03`

Priority:

- `Tier 3`

This is preserved only as an exploratory side case.

#### H3

- `hypothesis_id`: `H3`
- `priority_tier`: `Tier 3`
- `source_candidate_id`: `ecb_03`
- `pair_scope`: `ALL`
- `session_context`: `early New York`
- `structural_condition`: strongly expanded `sweep_high`
- `regime_condition`: `range_regime == strongly_expanded`
- `expected_directional_effect`: upside continuation
- `expected_holding_horizon`: `h4`

Formal hypothesis statement:

Some early-New-York upside sweeps inside strongly expanded states may continue higher rather than revert, but this is an exploratory side case rather than a main research path.

Market intuition:

This pattern may capture failed upside fade behavior when directional state is already strong, but its role is secondary because the reset evidence is cleaner on the downside family and on the pair-specific `USDJPY` branch.

Measurable predictions:

- aligned `h4` mean return should remain positive
- continuation fraction should stay above `0.60`
- the effect should remain positive across nearby horizons

Invalidation criteria:

- the effect merges back into the broader early-New-York family without staying distinct
- small structural shifts erase the continuation bias
- pooled support disappears once pair differences are handled explicitly

Risks / confounders:

- this may be a side effect of broader expanded-state continuation rather than a distinct sweep mechanism
- it risks distracting R10 away from the stronger downside family

Notes for later strategy design:

- R10 should only touch this after Tier 1 and Tier 2 planning is complete

## 4. Main vs Secondary Research Path

Main path:

- `H1A`
- `H1B`

These represent pooled downside continuation in strongly expanded London and early-New-York contexts. This is the primary direction for R10.

Secondary path:

- `H2`

This remains a separate `USDJPY` branch and should be planned as a pair-specific experiment family.

Exploratory-only path:

- `H3`

This should not become a top-level roadmap item unless later experiment design shows it adds distinct value.

## 5. Research Implications

R10 strategy experiment planning should start from:

1. one London downside continuation experiment family built from `H1A`
2. one early-New-York downside continuation experiment family built from `H1B`
3. one separate `USDJPY` upside continuation experiment family built from `H2`

The initial R10 experiments should:

- stay close to the R8 structural conditions
- avoid widening the candidate set
- use the invalidation criteria above as hard stop conditions

## 6. Limitations

- these are still research hypotheses, not executable strategies
- no costed strategy validation exists yet for these exact conditions
- pooled pair scope may still hide nuance inside the downside family
- the structural conditions are implementation-ready, but not yet entry/exit-complete
