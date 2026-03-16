# Statistical Reality Checks

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Source phases used:

- `R2` session structure
- `R3` volatility regime analysis
- `R4` structural extremes
- `R5` contextual structural breaches
- `R6` session-state transitions

Candidate patterns selected for stress-testing:

1. `lny_continuation_baseline`
2. `lny_expanded_london_continuation`
3. `expanded_contextual_breaches_h4`
4. `usdjpy_expanded_up_lny`
5. `low_vol_new_york_bias`

Artifacts:

- `outputs/diagnostics/statistical_reality_checks/candidate_patterns.csv`
- `outputs/diagnostics/statistical_reality_checks/reality_check_summary.csv`
- `outputs/diagnostics/statistical_reality_checks/yearly_stability_summary.csv`
- `outputs/diagnostics/statistical_reality_checks/pair_stability_summary.csv`
- `outputs/diagnostics/statistical_reality_checks/sensitivity_summary.csv`
- `outputs/diagnostics/statistical_reality_checks/sample_size_filter_summary.csv`

## 2. Why R7 Exists

R2 through R6 were deliberately descriptive. That means even the better-looking patterns could still be:

- small-sample artifacts
- pair-specific quirks hidden inside pooled summaries
- one-year effects
- definition-sensitive patterns that collapse under small changes

R7 is the hard filter before any formal hypothesis-writing phase.

## 3. Sample-Size Reality Check

All five candidate patterns passed the conservative base sample filters used in this phase:

- pooled patterns required at least `300` observations
- pair-specific patterns required at least `180`
- yearly buckets required at least `25` observations
- pooled cross-pair patterns required at least `120` observations in at least `2` pairs

Base sample counts:

- `expanded_contextual_breaches_h4`: `100,454`
- `lny_continuation_baseline`: `5,448`
- `lny_expanded_london_continuation`: `1,775`
- `low_vol_new_york_bias`: `1,586`
- `usdjpy_expanded_up_lny`: `324`

The sample-size problem was therefore not the main reason most patterns failed to survive as strong candidates. The bigger issues were effect quality, pair concentration, and friction sensitivity.

## 4. Yearly Stability

### Expanded contextual breaches

`expanded_contextual_breaches_h4` was the strongest pattern in the whole reality-check set:

- positive aligned mean outcome in all `7` years
- yearly continuation fractions clustered between roughly `0.536` and `0.566`
- no single year contributed more than `22.6%` of the total absolute effect

This is the cleanest case where an R4/R5 descriptive pattern still looks structurally persistent after a stricter filter.

### London -> New York baseline

`lny_continuation_baseline` did not survive:

- only `2` positive years versus `5` negative years
- pooled aligned mean outcome stayed slightly negative
- continuation fraction remained below `0.50` in most years

This matters because the descriptive continuation story from earlier phases was real at the fraction level, but not strong enough on aligned outcome once measured consistently and filtered conservatively.

### Expanded London -> New York

`lny_expanded_london_continuation` improved the descriptive picture, but not enough:

- `4` positive years versus `3` negative years
- pooled mean outcome stayed only slightly positive
- the effect remained too small for friction sanity

### Low-vol New York

`low_vol_new_york_bias` was mostly stable:

- `6` positive years out of `7`
- no one-year concentration problem

But it still failed the higher bar because the pooled effect remained too small once converted to a simple friction sanity proxy.

### USDJPY expanded-up London -> New York

`usdjpy_expanded_up_lny` was directionally interesting but thin:

- `5` positive years versus `2` negative years
- no one-year concentration problem
- still far below a simple `1` pip friction sanity threshold

## 5. Pair Stability

Pair stability is where the descriptive stories diverged most clearly.

### Expanded contextual breaches

This was the only candidate with genuinely broad cross-pair support:

- `EURUSD` mean aligned outcome: `0.000122`
- `GBPUSD` mean aligned outcome: `0.000182`
- `USDJPY` mean aligned outcome: `0.000160`

All three pairs stayed positive. `EURUSD` and `GBPUSD` also remained above the simple `1` pip sanity threshold, while `USDJPY` stayed positive but smaller in pip terms.

### London -> New York patterns

The pooled `london -> new_york` patterns did not hold evenly:

- `EURUSD` remained negative
- `GBPUSD` remained negative or near flat
- `USDJPY` was the only pair that stayed near flat to mildly positive

That means the pooled continuation story is not credible as a generic cross-pair effect.

### Low-vol New York

`low_vol_new_york_bias` is partly a pooling illusion:

- `EURUSD` and `GBPUSD` both stayed mildly positive
- `USDJPY` was materially stronger on raw session return and positive-close fraction

The effect is descriptive, but not cleanly transferable across pairs.

### USDJPY-specific continuation

`usdjpy_expanded_up_lny` stayed pair-specific by construction and did not gain enough magnitude to justify a stronger label.

## 6. Sensitivity Analysis

Small nearby definition changes were applied to each pattern:

- `london -> new_york` variants excluded compressed London states, restricted to medium/high-vol London states, or required a dominant structural breach
- expanded contextual breaches were split into breakout-only, sweep-only, and `48/96`-bar structural windows
- low-vol New York was loosened to low/medium vol, restricted to non-expanded ranges, or restricted to European pairs
- `USDJPY` expanded-up London carry was split into breakout-only, sweep-only, and medium/high-vol variants

Main result:

- `expanded_contextual_breaches_h4` survived all nearby definition changes with the same positive sign
- `lny_continuation_baseline` stayed stable in sign, but the sign was the wrong one: the aligned outcome remained negative
- `lny_expanded_london_continuation` stayed fragile in magnitude, not sign
- `low_vol_new_york_bias` kept a positive sign, but its friction profile remained weak
- `usdjpy_expanded_up_lny` failed because one nearby split (`sweep` only) collapsed the sample too sharply

## 7. Credibility Ranking

R7 uses four conservative labels:

- `fragile`
- `descriptive_only`
- `credible_candidate_for_hypothesis`
- `pair_specific_candidate`

Final ranking:

| pattern_id | label | reason |
| --- | --- | --- |
| `expanded_contextual_breaches_h4` | `credible_candidate_for_hypothesis` | positive across years, positive across all three pairs, and stable under small definition changes |
| `low_vol_new_york_bias` | `descriptive_only` | stable descriptively, but too small to survive a simple friction sanity check |
| `lny_expanded_london_continuation` | `descriptive_only` | better than the baseline, but still too weak and too pair-dependent |
| `usdjpy_expanded_up_lny` | `descriptive_only` | interesting pair-specific structure, but too thin and too small after sensitivity checks |
| `lny_continuation_baseline` | `descriptive_only` | aligned outcome stays negative despite acceptable sample size |

No candidate was promoted beyond structural-hypothesis credibility. Nothing in R7 should be read as a tradable edge.

## 8. Research Implications

The main lesson from R7 is that most of the earlier reset findings were real as descriptive structure, but not strong enough to survive a harder filter unchanged.

What should move into `R8`:

- expanded-range contextual breach behavior
- pair-specific `USDJPY` continuation structure, but only as a secondary, explicitly pair-specific line of inquiry
- low-vol New York behavior as a descriptive conditioning variable, not as a standalone directional candidate

What should not move forward as a lead idea:

- generic pooled `London -> New York` continuation
- generic expanded-London carry without additional context

## 9. Limitations

- R7 is still descriptive and structural, not strategy-validating
- multiple-testing risk still exists conceptually, even after narrowing the pattern set
- only `EURUSD`, `GBPUSD`, and `USDJPY` were included
- the friction sanity check is intentionally simple and conservative, not a full execution model
