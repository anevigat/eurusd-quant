# London Impulse to NY Reversal — Diagnostic Summary

## Strategy hypothesis

A strong London directional impulse may partially reverse when New York liquidity enters.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` valid days

## Diagnostic methodology

Script:

- `scripts/analyze_london_impulse_ny_reversal.py`

Windows:

- London impulse: `07:00-12:00 UTC`
- NY reversal window: `12:00-16:00 UTC`

Per day:

1. Compute London impulse (`london_close - london_open`)
2. Compute ATR(14) reference at end of London window
3. Label strong impulse when `impulse_size >= 1.0 * ATR`
4. Measure NY reversal and adverse move versus London close
5. Normalize both by London impulse size

## Summary results

- `days_analyzed`: `1817`
- `strong_london_impulse_frequency`: `0.7722`
- `bullish_impulse_frequency`: `0.4825`
- `bearish_impulse_frequency`: `0.5175`
- `median_reversal_ratio`: `0.7828`
- `p75_reversal_ratio`: `1.6914`
- `p90_reversal_ratio`: `3.0594`
- `median_adverse_move_ratio`: `0.8142`

## Interpretation

- Strong London impulses are frequent in this framing.
- NY reversal magnitude is non-trivial, but median adverse move is slightly larger than median reversal.
- The structure does not provide clear asymmetry for a robust standalone reversal edge.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/london_impulse_ny_reversal_diagnostic/summary.json`
- `outputs/london_impulse_ny_reversal_diagnostic/daily_metrics.csv`
- `outputs/london_impulse_ny_reversal_diagnostic/distribution.csv`
