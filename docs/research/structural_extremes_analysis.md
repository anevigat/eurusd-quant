# Structural Extremes And Liquidity Sweep Analysis

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Timeframe:

- `15m`

Sample period:

- `2018-01-01 22:00:00+00:00` through `2024-12-31 21:45:00+00:00`

Shared conventions reused from R2 and R3:

- UTC bar-open timestamps
- FX trading date anchored to the repo's `22:00 UTC` rollover
- sessions:
  - `asia`: `00:00-07:00 UTC`
  - `london`: `07:00-13:00 UTC`
  - `new_york`: `13:00-24:00 UTC`
- volatility regime from R3:
  - pair-specific, time-aware session realized-volatility buckets
  - trailing lookback `120` sessions
  - minimum history `30` sessions

Structural lookback windows:

- `24` bars
- `48` bars
- `96` bars

Structural definitions:

- `breakout_high`: current bar high exceeds the prior rolling high and the close remains at or above that prior high
- `breakout_low`: current bar low breaks the prior rolling low and the close remains at or below that prior low
- `sweep_high`: current bar high exceeds the prior rolling high but the close returns back below that prior high
- `sweep_low`: current bar low breaks the prior rolling low but the close returns back above that prior low

Forward-return horizons:

- `+1`, `+2`, `+4`, and `+8` bars

Outputs:

- `outputs/diagnostics/structural_extremes/extreme_event_inventory.csv`
- `outputs/diagnostics/structural_extremes/sweep_event_inventory.csv`
- `outputs/diagnostics/structural_extremes/post_extreme_forward_returns.csv`
- `outputs/diagnostics/structural_extremes/sweep_vs_breakout_summary.csv`
- `outputs/diagnostics/structural_extremes/session_sweep_behavior.csv`
- `outputs/diagnostics/structural_extremes/volatility_regime_sweep_behavior.csv`
- `outputs/diagnostics/structural_extremes/extreme_analysis_notes.json`

## 2. Structural Event Inventory

The first useful result is frequency: structural extremes are common, and sweeps are not rare exceptions.

Event counts by pair:

- `EURUSD`
  - `24`-bar breakouts: `18,411`
  - `24`-bar sweeps: `17,870`
  - `96`-bar breakouts: `7,806`
  - `96`-bar sweeps: `7,505`
- `GBPUSD`
  - `24`-bar breakouts: `18,349`
  - `24`-bar sweeps: `17,707`
  - `96`-bar breakouts: `8,004`
  - `96`-bar sweeps: `7,583`
- `USDJPY`
  - `24`-bar breakouts: `17,198`
  - `24`-bar sweeps: `16,473`
  - `96`-bar breakouts: `8,050`
  - `96`-bar sweeps: `7,466`

Sweep share is very stable across pairs and windows:

- `EURUSD`: roughly `49.0%` to `49.4%`
- `GBPUSD`: roughly `48.6%` to `49.1%`
- `USDJPY`: roughly `48.1%` to `48.9%`

Interpretation:

- structural breaches split almost evenly between confirmed closes beyond the level and immediate rejections back inside the range
- sweeps are a routine part of the path, not a niche subset

## 3. Sweep Vs Breakout Behavior

The main descriptive question in this phase was whether breakouts tend to continue and sweeps tend to revert. The answer is weaker and more pair-dependent than that simple story.

### Pooled behavior

At `96` bars and `+4` bars forward:

- `breakout_high` continuation probability: `0.4739`
- `breakout_high` reversal probability: `0.5236`
- `breakout_low` continuation probability: `0.4629`
- `breakout_low` reversal probability: `0.5354`
- `sweep_high` continuation probability: `0.4935`
- `sweep_high` reversal probability: `0.5037`
- `sweep_low` continuation probability: `0.4843`
- `sweep_low` reversal probability: `0.5139`

Interpretation:

- confirmed breakouts do not show clean follow-through on average
- sweeps do show more mean-reversion structure than breakouts, but the edge is modest rather than dramatic
- the strongest pooled result is simply that downside structural events reverse slightly more often than they continue

### Pair-level behavior

`EURUSD`:

- `96`-bar `breakout_high`, `+4` bars:
  - continuation `0.4521`
  - reversal `0.5448`
- `96`-bar `sweep_high`, `+4` bars:
  - continuation `0.4837`
  - reversal `0.5135`

`GBPUSD`:

- broadly similar to `EURUSD`
- `96`-bar `breakout_high`, `+4` bars:
  - continuation `0.4682`
  - reversal `0.5306`
- `96`-bar `sweep_high`, `+4` bars:
  - continuation `0.4928`
  - reversal `0.5041`

`USDJPY`:

- this is the only pair where higher-lookback upside structure looks even mildly continuation-friendly
- `96`-bar `breakout_high`, `+4` bars:
  - continuation `0.5014`
  - reversal `0.4952`
- `96`-bar `sweep_high`, `+4` bars:
  - continuation `0.5039`
  - reversal `0.4935`

Interpretation:

- `USDJPY` again looks structurally different from `EURUSD` and `GBPUSD`
- the European pairs are dominated by slight reversal after both upside and downside structural events
- even in `USDJPY`, the continuation effect is still small, not strong enough to treat as tradable evidence by itself

## 4. Session Interaction

Session context matters more for event frequency than for dramatic directional changes.

Pooled sweep frequency at `+4` bars:

`24`-bar sweeps:

- high-side sweep frequency per `1000` bars:
  - Asia `55.8`
  - London `64.2`
  - New York `40.2`
- low-side sweep frequency per `1000` bars:
  - Asia `53.9`
  - London `63.3`
  - New York `37.7`

`96`-bar sweeps:

- high-side sweep frequency per `1000` bars:
  - Asia `16.4`
  - London `28.2`
  - New York `22.8`
- low-side sweep frequency per `1000` bars:
  - Asia `14.2`
  - London `26.9`
  - New York `21.9`

Interpretation:

- London is the densest sweep session across all three structural windows
- New York carries more large-window sweeps than Asia, but far fewer short-window sweeps
- the strongest session effect here is event frequency, not a dramatic change in forward-return sign

Directional outcome by session is still muted:

- pooled London `96`-bar `sweep_high` at `+4` bars is nearly flat on mean return (`-0.000003`) with reversal probability `0.5007`
- pooled New York `96`-bar `sweep_high` is slightly positive (`0.000027`) with reversal probability `0.4961`
- pooled `96`-bar `sweep_low` remains slightly mean-reverting in every session

## 5. Volatility Interaction

R4 reused the R3 volatility-state classification to check whether sweeps are mostly low-vol phenomena or whether breakout persistence improves in high-vol states.

Main result:

- sweeps are not mostly low-vol events
- for many pair/window combinations, sweep frequency is actually highest in `high_vol` or `medium_vol`

Examples at `96` bars and `+4` bars:

`EURUSD`:

- `sweep_high` frequency per `1000` bars:
  - `low_vol` `15.1`
  - `medium_vol` `20.8`
  - `high_vol` `26.0`
- `sweep_low` frequency per `1000` bars:
  - `low_vol` `14.3`
  - `medium_vol` `24.8`
  - `high_vol` `27.3`

`GBPUSD`:

- same pattern, with strongest low-side sweep density in `high_vol`
- `96`-bar `sweep_low` mean forward return in `high_vol` is the weakest at `-0.000117`

`USDJPY`:

- high-side sweep returns stay positive in every volatility bucket:
  - `low_vol` `0.000027`
  - `medium_vol` `0.000070`
  - `high_vol` `0.000092`
- low-side sweep reversals remain common, especially in `low_vol` and `medium_vol`

Interpretation:

- sweep frequency rises with expansion rather than compression
- high-vol structural breaches do not rescue `EURUSD` or `GBPUSD` into clean breakout-continuation behavior
- `USDJPY` is again the one pair where high-vol structural highs look somewhat more persistent

## 6. Pair Differences

This phase reinforces the earlier reset-phase split:

- `EURUSD` and `GBPUSD` remain noisy around structural extremes
- `USDJPY` is more directionally stable around upside structural events

The clearest contrast is on higher-lookback upside events:

- `EURUSD` `96`-bar `breakout_high`, `+4` bars:
  - mean forward return `-0.000081`
  - reversal probability `0.5448`
- `GBPUSD` `96`-bar `breakout_high`, `+4` bars:
  - mean forward return `-0.000039`
  - reversal probability `0.5306`
- `USDJPY` `96`-bar `breakout_high`, `+4` bars:
  - mean forward return `0.000048`
  - continuation probability `0.5014`

`USDJPY` session examples:

- `96`-bar `sweep_high`, London, `+4` bars:
  - mean forward return `0.000068`
  - reversal probability `0.4872`
- `96`-bar `sweep_high`, New York, `+4` bars:
  - mean forward return `0.000083`
  - reversal probability `0.4857`

Interpretation:

- the `USDJPY` advantage is still modest, but it is consistent with R2 and R3
- structural-high behavior in `USDJPY` deserves more attention than the same setup in `EURUSD` or `GBPUSD`

## 7. Research Implications

Main lessons from R4:

- structural extremes are frequent and sweeps are nearly half of all breaches
- the simple rule of "breakouts continue, sweeps reverse" is too crude for these pairs
- `EURUSD` and `GBPUSD` show slight reversal bias after both breakouts and sweeps
- `USDJPY` is the only pair showing even mild continuation after higher-lookback upside extremes
- London is the highest-density sweep session, especially for larger structural windows
- sweeps are not primarily a low-volatility phenomenon; they often cluster more in medium and high volatility

Implications for later hypothesis generation:

- future structural ideas should distinguish upside from downside events and separate `USDJPY` from the European pairs early
- continuation hypotheses should likely focus on `USDJPY` and on upside structural events first
- mean-reversion hypotheses for `EURUSD` and `GBPUSD` should treat sweeps and confirmed breaks as related but not identical structures
- session-transition work should pay attention to London as the main structural-event generator

## 8. Limitations

- this phase is descriptive only
- no strategy rules, stop logic, or execution constraints were tested
- event frequencies are high enough to be informative, but the directional effects are still small in magnitude
- no significance or multiple-testing framework has been applied yet
