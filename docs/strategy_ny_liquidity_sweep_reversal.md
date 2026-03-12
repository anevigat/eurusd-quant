# NY Liquidity Sweep Reversal — Diagnostic Summary

## Strategy hypothesis

When NY session price action sweeps the London range extremes, liquidity grabs may lead to mean-reversion rather than continuation.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` days with valid London+NY windows

## Diagnostic methodology

Script:

- `scripts/analyze_ny_liquidity_sweep_reversal.py`

Windows:

- London reference range: `07:00-13:00 UTC`
- NY sweep window: `13:00-16:00 UTC`

Per day:

1. Compute London high/low
2. Detect first NY sweep above/below London range
3. Measure post-sweep reversal and continuation moves
4. Normalize by London range:
   - `reversal_ratio`
   - `follow_through_ratio`

## Summary results

- `days_analyzed`: `1817`
- `sweep_frequency`: `0.8090`
- `sweep_above_frequency`: `0.4782`
- `sweep_below_frequency`: `0.5218`
- `median_reversal_ratio`: `0.3527`
- `median_follow_through_ratio`: `0.3281`
- `reversal_dominates_frequency`: `0.5279`

## Interpretation

- NY sweeps are frequent, but reversal advantage over continuation is modest.
- Median reversal and follow-through are close, with only slight reversal dominance.
- The structure looks too weak for a clean standalone reversal strategy.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation in current form.

## Outputs

- `outputs/ny_liquidity_sweep_reversal_diagnostic/summary.json`
- `outputs/ny_liquidity_sweep_reversal_diagnostic/daily_metrics.csv`
- `outputs/ny_liquidity_sweep_reversal_diagnostic/distribution.csv`
