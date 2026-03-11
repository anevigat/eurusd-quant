# VWAP Intraday Reversion — Diagnostic Research Summary

## 1. Strategy hypothesis

Hypothesis:

- when price moves far enough away from intraday VWAP, it may mean-revert back toward VWAP later in the session
- larger deviations (in ATR units) should show stronger short-horizon reversion than smaller deviations

This diagnostic focuses on structure only, before any strategy implementation.

## 2. Dataset used

- Instrument: EURUSD
- Timeframe: 15m bars
- Dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## 3. Diagnostic methodology

Implemented in:

- `scripts/analyze_vwap_intraday_reversion.py`

Session scope:

- full day data used for intraday VWAP construction (`00:00-23:45 UTC`)
- active analysis window: `07:00-17:00 UTC` (`[start, end)`)

VWAP method:

- no traded volume is available in standard bars
- used cumulative average of typical price per day as a VWAP proxy:
  - `typical_price = (mid_high + mid_low + mid_close) / 3`
  - intraday VWAP proxy = cumulative mean of typical price from `00:00` onward

Deviation and normalization:

- `deviation = mid_close - intraday_vwap`
- `deviation_atr = deviation / ATR(14)`
- buckets by `abs(deviation_atr)` quantiles:
  - `small_dev <= p50`
  - `medium_dev (p50, p75]`
  - `large_dev (p75, p90]`
  - `extreme_dev > p90`

Reversion measurement:

- lookahead horizons:
  - next 4 bars (1 hour)
  - next 8 bars (2 hours)
- `reversion_ratio = (abs(dev_now) - abs(dev_horizon)) / abs(dev_now)`
  - `> 0`: moved toward VWAP
  - `< 0`: moved further away

## 4. Summary results

Global:

- `bars_analyzed`: `72,696`
- `median_abs_deviation_atr`: `1.6633`
- `p75_abs_deviation_atr`: `2.7902`
- `p90_abs_deviation_atr`: `3.9346`

Bucket medians (4-bar / 8-bar reversion):

- `small_dev`: `-0.4827 / -0.8217`
- `medium_dev`: `0.0726 / 0.0971`
- `large_dev`: `0.0816 / 0.1314`
- `extreme_dev`: `0.0785 / 0.1350`

Sign split medians:

- positive deviations:
  - 4 bars: `-0.0492`
  - 8 bars: `-0.0953`
- negative deviations:
  - 4 bars: `-0.0549`
  - 8 bars: `-0.1045`

## 5. Interpretation

Key observations:

- deviations are frequent and often substantial in ATR terms
- small deviations mostly continue away from VWAP (negative median reversion)
- medium/large/extreme buckets show positive median reversion over 4-8 bars
- reversion signal exists but is modest in magnitude (median ratios near `0.08-0.14` for larger buckets)

Interpretation:

- the effect looks directionally real for stretched states, but not strong enough yet to imply a robust standalone edge without additional filters and execution constraints.

## 6. Conclusion

Classification:

- promising enough to implement as MVP

Rationale:

- larger deviations revert positively on median over both 1-hour and 2-hour horizons
- deviations occur frequently enough to support strategy feasibility testing
- effect size is moderate, so any future MVP should remain conservative and cost-aware

## 7. Final status

- diagnostic research completed
- no strategy implementation added in this phase
- next step can be a small, controlled MVP strategy test

## Outputs

- `outputs/vwap_intraday_reversion_diagnostic/summary.json`
- `outputs/vwap_intraday_reversion_diagnostic/daily_metrics.csv`
- `outputs/vwap_intraday_reversion_diagnostic/distribution.csv`
