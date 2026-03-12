# Asia Drift -> London Reversal — Diagnostic Summary

## Strategy hypothesis

If the Asian session drifts directionally (`00:00-07:00 UTC`), London open (`07:00-10:00 UTC`) may reverse that drift enough to support a mean-reversion setup.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1822` trading days

## Diagnostic methodology

Script:

- `scripts/analyze_asia_drift_london_reversal.py`

Daily process:

1. Asian drift: `asia_close - asia_open` (`00:00-07:00`)
2. London reversal: move against drift during `07:00-10:00`
3. London follow-through: move in drift direction during `07:00-10:00`
4. Ratios normalized by Asian drift magnitude:
   - `reversal_ratio`
   - `follow_through_ratio`
   - `adverse_move_ratio`

## Summary results

- `days_analyzed`: `1822`
- `up_drift_frequency`: `0.4923`
- `down_drift_frequency`: `0.5060`
- `median_reversal_ratio`: `1.2687`
- `median_follow_through_ratio`: `1.1866`
- `median_adverse_move_ratio`: `1.2687`
- `reversal_dominates_frequency`: `0.5113`

## Interpretation

- Reversal and continuation magnitudes are both large and close to each other.
- Reversal dominance is only slightly above coin-flip (`~51%`), indicating weak directional asymmetry.
- The structure does not show a clean, stable edge for a simple London reversal implementation.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation at this stage.

## Final status

- diagnostic script added
- outputs generated
- documented in research index and strategy matrix

## Outputs

- `outputs/asia_drift_london_reversal_diagnostic/summary.json`
- `outputs/asia_drift_london_reversal_diagnostic/daily_metrics.csv`
- `outputs/asia_drift_london_reversal_diagnostic/distribution.csv`
