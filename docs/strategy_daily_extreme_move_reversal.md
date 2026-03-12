# Daily Extreme Move Reversal — Diagnostic Summary

## Strategy hypothesis

After unusually large daily directional moves, the next day may mean-revert more often than it continues.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Diagnostic methodology

Script:

- `scripts/analyze_daily_extreme_move_reversal.py`

Process:

1. Aggregate M15 bars to daily OHLC
2. Compute daily ATR(14)
3. Flag strong momentum days where `abs(daily_return) >= 1.0 * daily_ATR`
4. Measure next-day continuation vs reversal relative to signal-day direction
5. Normalize by ATR (`continuation_1d_atr`, `reversal_1d_atr`)

## Summary results

- `days_analyzed`: `2190`
- `strong_momentum_frequency`: `0.1315`
- `reversal_probability_1d`: `0.5417`
- `continuation_probability_1d`: `0.4549`
- `median_reversal_1d_atr`: `0.0287`
- `median_continuation_1d_atr`: `-0.0287`

## Interpretation

- Reversal probability is above 50%, but only modestly.
- Median reversal magnitude is very small (`~0.03 ATR`), likely too weak after costs/slippage.
- The edge signal exists directionally but is economically weak in this simple form.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation in current form.

## Outputs

- `outputs/daily_extreme_move_reversal_diagnostic/summary.json`
- `outputs/daily_extreme_move_reversal_diagnostic/daily_metrics.csv`
- `outputs/daily_extreme_move_reversal_diagnostic/distribution.csv`
