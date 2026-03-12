# Session VWAP Reversion — Diagnostic Summary

## Strategy hypothesis

Price may revert toward session VWAP after large deviations, especially around London/NY liquidity
transitions.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- observations: `72684` bars

## Diagnostic methodology

Script:

- `scripts/analyze_session_vwap_reversion.py`

Setup:

- sessions: London `07:00-12:00 UTC`, NY `12:00-17:00 UTC`
- session VWAP proxy: cumulative mean of session typical price
- deviation metric: `deviation_atr = (mid_close - session_vwap) / ATR(14)`
- reversion horizons: `4` bars and `8` bars
- buckets by absolute deviation ATR quantiles:
  - `small_dev` <= p50
  - `medium_dev` p50-p75
  - `large_dev` p75-p90
  - `extreme_dev` > p90

## Summary results

- `bars_analyzed`: `72684`
- `median_abs_deviation_atr`: `0.7268`
- `p75_abs_deviation_atr`: `1.3378`
- `p90_abs_deviation_atr`: `2.0210`
- `median_reversion_ratio_4bars`: `-0.2611`
- `median_reversion_ratio_8bars`: `-0.6169`

Bucket pattern:

- `large_dev` median reversion: `0.2503` (4 bars), `0.3195` (8 bars)
- `extreme_dev` median reversion: `0.2751` (4 bars), `0.4287` (8 bars)

## Interpretation

- Unfiltered session-VWAP reversion is weak (negative median reversion overall).
- Reversion behavior improves materially in the large/extreme deviation buckets.
- The effect is highly conditional and too noisy in the full sample.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/session_vwap_reversion_diagnostic/summary.json`
- `outputs/session_vwap_reversion_diagnostic/daily_metrics.csv`
- `outputs/session_vwap_reversion_diagnostic/distribution.csv`
