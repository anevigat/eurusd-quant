# Contextual Structural Breach Analysis

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Timeframe:

- `15m`

Sample period:

- `2018-01-01 22:00:00+00:00` through `2024-12-31 21:45:00+00:00`

Context variables used:

- `session`
- `bar_index_within_session`
- `session_subcontext`: `early_session`, `mid_session`, `late_session`
- `transition_context`:
  - `inside_asia`
  - `asia_to_london_boundary`
  - `inside_london`
  - `london_to_new_york_boundary`
  - `inside_new_york`
- `volatility_regime` from R3:
  - pair-specific, time-aware session realized-volatility buckets
- `range_regime` from R2 normalization:
  - `compressed`, `normal`, `expanded`
- `breach_magnitude_price`
- `breach_magnitude_pips`
- `breach_magnitude_atr`
- `magnitude_bucket`: `small`, `medium`, `large`
- `pair`, `event_type`, and `lookback_window`

Structural events reused from R4:

- `breakout_high`
- `breakout_low`
- `sweep_high`
- `sweep_low`

Forward outcome horizons:

- `+1`, `+2`, `+4`, and `+8` bars

Outputs:

- `outputs/diagnostics/contextual_breaches/contextual_breach_inventory.csv`
- `outputs/diagnostics/contextual_breaches/contextual_breach_outcomes.csv`
- `outputs/diagnostics/contextual_breaches/breach_outcomes_by_session_context.csv`
- `outputs/diagnostics/contextual_breaches/breach_outcomes_by_volatility_context.csv`
- `outputs/diagnostics/contextual_breaches/breach_outcomes_by_range_context.csv`
- `outputs/diagnostics/contextual_breaches/breach_outcomes_by_magnitude_bucket.csv`
- `outputs/diagnostics/contextual_breaches/breach_outcomes_by_pair.csv`
- `outputs/diagnostics/contextual_breaches/breach_context_notes.json`

## 2. Why R5 Exists

R4 showed that the generic mapping

- breach -> continuation
- sweep -> reversal

was too weak to be useful on its own.

The key question for R5 was whether the post-breach path depends on context:

- where the breach happens in the session
- whether it occurs near a session boundary
- what volatility state the market is already in
- whether the prior session structure is compressed or expanded
- whether the breach is small or large relative to ATR

The answer is yes. Context does not create a large standalone edge, but it does materially change the sign and persistence of post-breach behavior.

## 3. Session-Timing Context

This is the clearest timing result of the phase.

### Boundary and early-session effects

At `96` bars and `+4` bars forward, the strongest pooled continuation contexts are:

- `sweep_high`, early New York, `london_to_new_york_boundary`
  - continuation `0.5904`
  - reversal `0.4036`
  - sample count `166`
- `sweep_low`, early New York, `london_to_new_york_boundary`
  - continuation `0.5263`
  - reversal `0.4737`
  - sample count `133`
- `sweep_high`, early New York, `inside_new_york`
  - continuation `0.5234`
  - reversal `0.4747`
  - sample count `1603`

Other notable timing cells:

- `breakout_high`, early London, `asia_to_london_boundary`
  - continuation `0.5086`
  - reversal `0.4885`
  - sample count `696`
- `breakout_high`, early New York, `inside_new_york`
  - continuation `0.5029`
  - reversal `0.4959`
  - sample count `1700`

### Late-session weakness

The strongest pooled reversal contexts are concentrated in:

- late New York
- Asia mid/late session
- New York boundary downside breaks

Examples at `96` bars and `+4` bars:

- `breakout_low`, early New York, `london_to_new_york_boundary`
  - continuation `0.3750`
  - reversal `0.6250`
  - sample count `160`
- `breakout_low`, late New York, `inside_new_york`
  - continuation `0.4139`
  - reversal `0.5832`
  - sample count `1034`
- `sweep_high`, late New York, `inside_new_york`
  - continuation `0.4256`
  - reversal `0.5702`
  - sample count `1210`

Interpretation:

- the first part of New York behaves differently from late New York
- some of the better breach-follow-through appears near the London-to-New York handoff
- late-session breaches, especially in New York, are more likely to unwind than extend

## 4. Volatility Context

Volatility still mostly changes magnitude, not generic directionality, but context makes the nuance clearer than in R4.

### Pooled view

At `96` bars and `+4` bars:

- high volatility does not rescue all breakouts into continuation
- low-vol and medium-vol contexts can still fail badly depending on session and breach direction
- the main effect of volatility is conditional, not monotonic

Examples:

- pooled `breakout_high`, London, `low_vol`
  - mean aligned return `0.000107`
  - continuation `0.5313`
  - reversal `0.4687`
- pooled `breakout_high`, New York, `high_vol`
  - mean aligned return `-0.000052`
  - continuation `0.4892`
  - reversal `0.5087`
- pooled `sweep_high`, New York, `low_vol`
  - mean aligned return `0.000056`
  - continuation `0.5193`
  - reversal `0.4755`

Interpretation:

- high volatility by itself is not enough
- some favorable breach behavior appears in low-vol or medium-vol timing-specific contexts
- this is consistent with R3: volatility state affects behavior, but mostly through interaction with other structure

## 5. Range Context

This is the strongest contextual result in the entire phase.

### Expanded regimes

Expanded regimes flip many breach types from reversal-dominated to mildly continuation-friendly.

Pooled `96`-bar, `+4` bar examples:

- `breakout_high`, London, `expanded`
  - mean aligned return `0.000195`
  - continuation `0.5691`
  - reversal `0.4295`
- `breakout_high`, New York, `expanded`
  - mean aligned return `0.000138`
  - continuation `0.5568`
  - reversal `0.4404`
- `sweep_high`, New York, `expanded`
  - mean aligned return `0.000188`
  - continuation `0.5559`
  - reversal `0.4422`
- `sweep_low`, London, `expanded`
  - mean aligned return `0.000196`
  - continuation `0.5506`
  - reversal `0.4476`

### Compressed regimes

Compressed regimes are the opposite:

- `breakout_high`, London, `compressed`
  - continuation `0.3365`
  - reversal `0.6619`
- `breakout_low`, New York, `compressed`
  - continuation `0.2881`
  - reversal `0.7119`
- `sweep_high`, New York, `compressed`
  - continuation `0.3959`
  - reversal `0.6000`
- `sweep_low`, Asia, `compressed`
  - continuation `0.3211`
  - reversal `0.6758`

Interpretation:

- prior range state matters more than the raw event label
- in compressed regimes, breaches are much more likely to fail
- in expanded regimes, even sweeps can become more continuation-like than mean-reverting

This is the clearest structural lesson from R5.

## 6. Breach Magnitude

Breach size matters, but less than range regime.

Pooled `96`-bar, `+4` bar examples:

- `breakout_high`
  - `small`: continuation `0.4660`
  - `medium`: continuation `0.4810`
  - `large`: continuation `0.4799`
- `sweep_high`
  - `small`: continuation `0.5066`
  - `medium`: continuation `0.4869`
  - `large`: continuation `0.4885`
- `sweep_low`
  - `small`: continuation `0.4774`
  - `medium`: continuation `0.4846`
  - `large`: continuation `0.4937`

Interpretation:

- larger breaches do not simply mean exhaustion
- they also do not reliably mean stronger continuation across all pairs
- magnitude is useful, but secondary to range regime and timing context

## 7. Pair Differences

The pair split remains central.

### EURUSD

`EURUSD` still looks mostly noisy around breaches, but context helps isolate a few milder continuation zones:

- `sweep_low`, early London inside the session:
  - continuation `0.5487`
  - sample count `226`
- `sweep_low`, early New York inside the session:
  - continuation `0.5386`
  - sample count `518`

But the broader pattern remains weak:

- `breakout_high`, `96`-bar, `+4` bars:
  - mean aligned return `-0.000081`
  - continuation `0.4521`
- large `EURUSD breakout_high` breaches are even worse:
  - continuation `0.4322`

### GBPUSD

`GBPUSD` is similar to `EURUSD`, but some boundary highs improve:

- `sweep_high`, early New York boundary:
  - continuation `0.6792`
  - sample count `53`
- `sweep_high`, early New York inside the session:
  - continuation `0.5434`
  - sample count `495`

Still, the broader baseline remains slightly reversal-biased:

- `breakout_high`, `96`-bar, `+4` bars:
  - continuation `0.4682`
- Asia mid-session highs are among the weakest contexts:
  - continuation `0.3427`

### USDJPY

`USDJPY` remains the most continuation-friendly pair, especially on upside structure:

- `breakout_high`, `96`-bar, `+4` bars:
  - continuation `0.5014`
  - reversal `0.4952`
- `sweep_high`, `96`-bar, `+4` bars:
  - continuation `0.5039`
  - reversal `0.4935`

Best `USDJPY` contexts:

- `breakout_high`, late London inside the session:
  - continuation `0.5556`
  - mean aligned return `0.000201`
- `breakout_high`, early New York inside the session:
  - continuation `0.5458`
  - mean aligned return `0.000143`
- `sweep_high`, early New York boundary:
  - continuation `0.5882`
  - sample count `68`

Interpretation:

- `USDJPY` is genuinely more continuation-friendly than `EURUSD` or `GBPUSD`
- but even here the favorable contexts are specific rather than universal

## 8. Research Implications

Main lessons from R5:

- the breach itself is not the main explanatory variable
- range regime is the strongest context layer
- expanded contexts are much more continuation-friendly than compressed contexts
- early New York and some boundary cells are materially different from late New York
- magnitude helps, but does not dominate the sign of the outcome
- `USDJPY` should not be grouped with `EURUSD` and `GBPUSD` when generating later hypotheses

What this suggests for later hypothesis generation:

- continuation work should focus on expanded-range contexts first
- late-session breaches, especially in New York, are better treated as exhaustion candidates than as continuation candidates
- London-to-New York handoff behavior deserves explicit follow-up, especially for upside sweeps
- `USDJPY` likely needs separate structural hypothesis families rather than pooled G10-style templates

## 9. Limitations

- this is still descriptive research only
- no formal significance or multiple-testing layer has been applied yet
- only `EURUSD`, `GBPUSD`, and `USDJPY` were included
- some boundary cells remain small and should not drive conclusions by themselves
