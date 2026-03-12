# Session Liquidity Sweep Reversal — Diagnostic Summary

## Strategy hypothesis

When price sweeps a prior session high/low, liquidity may be consumed and price may reverse more than it continues.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1822` days

## Diagnostic methodology

Script:

- `scripts/analyze_session_liquidity_sweep_reversal.py`

Windows:

- reference session: `00:00-07:00 UTC`
- sweep window: `07:00-10:00 UTC`

Per day:

1. Compute reference high/low from `00:00-07:00`
2. Detect first sweep in `07:00-10:00` (above or below)
3. Measure post-sweep:
   - reversal move
   - continuation move
4. Normalize by reference range:
   - `reversal_ratio`
   - `follow_through_ratio`

## Summary results

- `days_analyzed`: `1822`
- `sweep_frequency`: `0.9171`
- `sweep_above_frequency`: `0.5075`
- `sweep_below_frequency`: `0.4925`
- `median_reversal_ratio`: `0.5195`
- `median_follow_through_ratio`: `0.4606`
- `reversal_dominates_frequency`: `0.5183`

## Interpretation

- Sweeps are very frequent, but the reversal-vs-continuation edge is weak.
- Median reversal is only modestly higher than median continuation.
- Reversal dominance near `52%` is not strong enough to justify an unfiltered MVP.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation in current form.

## Outputs

- `outputs/session_liquidity_sweep_reversal_diagnostic/summary.json`
- `outputs/session_liquidity_sweep_reversal_diagnostic/daily_metrics.csv`
- `outputs/session_liquidity_sweep_reversal_diagnostic/distribution.csv`
