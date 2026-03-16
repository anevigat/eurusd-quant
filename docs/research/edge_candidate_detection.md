# Edge Candidate Detection

## 1. Scope

R8 takes the only R7 survivor, `expanded_contextual_breaches_h4`, and converts it into a small set of precise edge-candidate definitions that are ready for formal hypothesis writing in `R9`.

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

This phase does not implement strategies. It only narrows the surviving structural region into specific candidate conditions.

Artifacts:

- `outputs/diagnostics/edge_candidates/candidate_region_inventory.csv`
- `outputs/diagnostics/edge_candidates/candidate_region_subregions.csv`
- `outputs/diagnostics/edge_candidates/candidate_outcome_profiles.csv`
- `outputs/diagnostics/edge_candidates/candidate_pair_breakdown.csv`
- `outputs/diagnostics/edge_candidates/candidate_time_of_day_breakdown.csv`
- `outputs/diagnostics/edge_candidates/candidate_regime_breakdown.csv`
- `outputs/diagnostics/edge_candidates/edge_candidate_definitions.csv`

## 2. Base Candidate Region

The R8 base region is the exact R7 definition:

- source pattern: `expanded_contextual_breaches_h4`
- event universe: contextual structural breach events from `R5`
- range filter: `range_regime == expanded`
- breach types included:
  - `breakout_high`
  - `breakout_low`
  - `sweep_high`
  - `sweep_low`
- structural lookbacks included:
  - `24`
  - `48`
  - `96`
- evaluation anchor: aligned `+4` bar outcome

This base region contains `100,454` events.

Base `+4` bar profile:

- mean aligned return: `0.000154`
- continuation fraction: `0.5497`
- positive raw-return fraction: `0.5027`

Interpretation:

- the signal is not a generic “always bullish” effect
- it is a directional follow-through effect once outcomes are aligned to breach direction

## 3. Subregion Exploration

The strongest structural splits were not pair-only. The main differentiator was **time context inside the expanded region**, followed by **expanded-intensity** and then breach subtype.

### Strongly expanded vs moderately expanded

Expanded intensity was the clearest amplifier:

- `strongly_expanded`: mean `+4` aligned return `0.000290`, continuation `0.5706`
- `moderately_expanded`: mean `+4` aligned return `0.000086`, continuation `0.5393`

So R8 treats `strongly_expanded` as the primary candidate slice.

### Time-of-day structure

Main `+4` bar time-context results:

- `early New York`: mean `0.000235`, continuation `0.5728`
- `London`: mean `0.000206`, continuation `0.5661`
- `Asia`: mean `0.000110`, continuation `0.5428`
- `New York` full-session remainder: mean `0.000094`, continuation `0.5254`

The `London -> New York boundary` bucket had only `5` events in this exact base region and is too small to drive conclusions.

### Pair structure

Pair-level `+4` bar aligned means:

- `GBPUSD`: `0.000182`
- `USDJPY`: `0.000160`
- `EURUSD`: `0.000122`

The candidate is not driven by one pair only. `GBPUSD` is strongest on the pooled downside-structure candidates, while `USDJPY` remains the best exploratory pair for upside continuation.

## 4. Payoff Structure

The base region payoff is not strongest immediately. It tends to build over the next few bars.

Base aligned mean return by horizon:

- `+1`: `0.000059`
- `+2`: `0.000094`
- `+4`: `0.000154`
- `+8`: `0.000209`

The same pattern appears in the top candidate slices:

- the better candidates are already positive at `+1`
- they usually strengthen into `+4`
- most stay positive at `+8`

That implies the candidate is not just a one-bar microstructure bounce. It looks more like short-horizon directional follow-through after an already-expanded breach event.

One important interpretation detail:

- downside breach candidates often have low **raw** positive-return fractions because favorable continuation after a downside breach is a negative raw return
- for those candidates, the more useful metric is `continuation_fraction` and the aligned-return profile

## 5. Pair Differences

### Pooled primary structure

The pooled candidate remains valid because all three pairs stay positive in the base region and in the stronger London / early-New-York slices.

### USDJPY exploratory thread

`USDJPY` still shows a distinct upside-continuation shape:

- the best surviving pair-specific candidate in R8 is an upside breakout continuation slice
- that is different from the pooled European-pair-heavy downside continuation candidates

So R9 should keep:

- one pooled hypothesis family
- one explicitly pair-specific `USDJPY` exploratory family

## 6. Top Candidate Definitions

R8 promotes the following precise candidate definitions for `R9`.

| candidate_id | pair_scope | session_context | range_regime | breach_type | magnitude_bucket | horizon | sample_count | mean_outcome | continuation_fraction |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| `ecb_01` | `ALL` | `London` | `strongly_expanded` | `breakout_low` | `small` | `h4` | `596` | `0.000848` | `0.6980` |
| `ecb_02` | `ALL` | `London` | `strongly_expanded` | `sweep_low` | `medium` | `h4` | `485` | `0.000753` | `0.6557` |
| `ecb_03` | `ALL` | `early New York` | `strongly_expanded` | `sweep_high` | `small` | `h4` | `547` | `0.000495` | `0.6088` |
| `ecb_04` | `ALL` | `early New York` | `strongly_expanded` | `sweep_low` | `medium` | `h4` | `575` | `0.000562` | `0.6400` |
| `ecb_05` | `USDJPY` | `New York` | `strongly_expanded` | `breakout_high` | `small` | `h4` | `722` | `0.000180` | `0.5900` |

Interpretation:

- `ecb_01` and `ecb_02` are the cleanest pooled London downside-continuation candidates
- `ecb_03` and `ecb_04` show that early New York still matters, but with breach-type asymmetry
- `ecb_05` is the secondary pair-specific continuation candidate for `USDJPY`

## 7. Research Implications

R8 narrows the next phase substantially.

What should move into `R9`:

- pooled strongly-expanded London downside-breach hypotheses
- pooled strongly-expanded early-New-York sweep hypotheses
- a separate `USDJPY` upside-breakout exploratory hypothesis

What should not move into `R9`:

- generic “all expanded contextual breaches” rules without time-context narrowing
- moderately expanded versions of the same pattern as a lead candidate family
- generic pooled upside breakout continuation without pair-specific structure

## 8. Limitations

- these are still structural candidate definitions, not trading rules
- no out-of-sample strategy validation has been done yet on these exact definitions
- the candidate set is intentionally narrow and may still contain multiple-testing residue
- the `London -> New York boundary` bucket remained too small in this exact event region to support a standalone candidate
