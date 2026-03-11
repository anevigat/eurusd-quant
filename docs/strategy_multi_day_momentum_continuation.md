# Multi-day Momentum Continuation — Diagnostic Research Summary

## 1. Strategy hypothesis

Hypothesis:

- very large directional daily moves may show short-term persistence
- after a strong momentum day, price may continue in the same direction over the next 1-3 trading days

The diagnostic goal was to test if that persistence is strong enough to justify a later MVP strategy.

## 2. Dataset used

- Instrument: EURUSD
- Timeframe source: 15m bars aggregated to daily bars
- Dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## 3. Diagnostic methodology

Implemented in:

- `scripts/analyze_multi_day_momentum_continuation.py`

Daily bar construction:

- `daily_open`, `daily_high`, `daily_low`, `daily_close`
- `daily_range = daily_high - daily_low`
- `daily_return = daily_close - daily_open`
- `daily_ATR(14)` via true range on daily bars

Momentum event definition:

- strong momentum day: `abs(daily_return) >= 1.0 * daily_ATR`
- ratio tracked: `daily_return_atr = abs(daily_return) / daily_ATR`
- direction:
  - `bullish_momentum` if `daily_return > 0`
  - `bearish_momentum` if `daily_return < 0`

Forward continuation:

- `continuation_1d`, `continuation_2d`, `continuation_3d` from signal close
- direction-adjusted (bullish and bearish symmetric)
- normalized as `continuation_Nd_atr = continuation_Nd / daily_ATR`

Adverse movement:

- computed over next `N` days and normalized by signal-day ATR

## 4. Summary results

Core frequencies:

- `days_analyzed`: `2190`
- `strong_momentum_frequency`: `0.1292`
- `bullish_momentum_frequency`: `0.5027`
- `bearish_momentum_frequency`: `0.4968`

Daily return strength:

- `median_daily_return_atr`: `0.3693`
- `p75_daily_return_atr`: `0.7269`
- `p90_daily_return_atr`: `1.0885`

Strong-momentum continuation:

- `strong_momentum_days`: `283`
- `median_continuation_1d_atr`: `-0.0269`
- `median_continuation_2d_atr`: `-0.0833`
- `median_continuation_3d_atr`: `-0.0800`
- `p75_continuation_1d_atr`: `0.3126`
- `p75_continuation_2d_atr`: `0.5220`
- `p75_continuation_3d_atr`: `0.6280`

Directional asymmetry check:

- `strong_bullish_median_continuation_1d_atr`: `-0.1420`
- `strong_bearish_median_continuation_1d_atr`: `0.0181`

## 5. Interpretation

Findings:

- strong momentum days occur, but not at very high frequency (~12.9%)
- median follow-through over 1-3 days is negative, not positive
- upper quantiles show occasional continuation, but the median behavior is weak
- bullish and bearish strong-momentum continuation is asymmetric

Interpretation:

- persistence exists in tails, but the central tendency does not support a robust continuation edge
- a simple momentum continuation implementation would likely be noise-dominated

## 6. Conclusion

Classification:

- researched but not promising

Reason:

- median 1-3 day continuation after strong momentum is negative
- no clear evidence that longer holding windows improve continuation on median

## 7. Final status

- diagnostic research completed
- no strategy implementation added
- current concept is not recommended for MVP in its present form

## Outputs

- `outputs/multi_day_momentum_continuation_diagnostic/summary.json`
- `outputs/multi_day_momentum_continuation_diagnostic/daily_metrics.csv`
- `outputs/multi_day_momentum_continuation_diagnostic/distribution.csv`
