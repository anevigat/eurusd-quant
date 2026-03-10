# False Breakout Reversal Strategy Research Summary

## Strategy hypothesis

Original hypothesis:

- define Asian range with `00:00-06:00 UTC`
- detect a false breakout of Asian high/low
- wait for price to close back inside the range
- enter a reversal trade
- focus execution in early London session

Motivation:

- the prior raw Asian breakout continuation idea appeared weak on EURUSD
- this strategy tested the opposite hypothesis (failed breakout mean reversion)

## Implementation summary

Implemented MVP strategy:

- `strategy`: `false_breakout_reversal`
- one trade per day
- ATR minimum filter
- configurable `allowed_side` (`both`, `long_only`, `short_only`)
- configurable exit models:
  - `range_midpoint`
  - `fixed_r`
  - `atr_target`

## Dataset(s) used

Main research datasets:

- EURUSD M15 bid/ask-aware bars
- 2023 data for smoke tests and early diagnostics
- combined 2018-2024 dataset for multi-year validation

Pipeline basis:

- Dukascopy tick data
- cleaned ticks converted to bid/ask-aware M15 bars

## Experiments performed

1. Initial smoke backtest
2. Behavior diagnostics
   - trade distribution
   - exit reasons
   - average win/loss
   - long vs short
   - entry-hour analysis
   - MFE/MAE analysis
3. Side and time-window segmentation
4. Exit-model comparison
   - `range_midpoint`
   - `fixed_r`
   - `atr_target`
5. Multi-year validation (2018-2024)
6. Regime analysis
   - pre-London drift
7. Drift-down + short-only refinement

## Key findings

- performance was much stronger in `08:00-09:00 UTC` than adjacent entry windows
- exit structure mattered; `atr_target` was best among tested exit variants
- the concept showed some signal, but not as a robust unconditional strategy
- multi-year validation showed clear regime dependence
- pre-London downward drift improved aggregate performance
- short-only inside drift-down improved some metrics (notably PF/expectancy)
- even with filtering, robustness remained insufficient for deployment-level confidence

## Final conclusion

The `false_breakout_reversal` strategy appears to contain some structural signal, but the edge is too narrow, too regime-dependent, and too weak after filtering to justify continued refinement at this stage.

Classification:

- researched but not robust

## Lessons learned

- time-of-day effects are strong in EURUSD intraday systems
- overnight/pre-London drift can be a useful contextual variable
- side asymmetry can materially affect results
- exit logic can significantly change headline metrics
- regime filters should be tested one at a time with frozen baselines

## Future revisit options

- test the same hypothesis on other FX pairs
- retest under materially different macro regimes
- combine with a fundamentally different context filter (not minor parameter tuning)
- revisit only if future diagnostics show stronger raw excursion structure

## Related outputs

Primary result folders:

- `outputs/false_breakout_reversal_smoke/`
- `outputs/false_breakout_reversal_diagnostics/`
- `outputs/false_breakout_reversal_segmentation/`
- `outputs/false_breakout_exit_models/`
- `outputs/false_breakout_pre_london_drift/`
- `outputs/false_breakout_drift_down_short_only/`
