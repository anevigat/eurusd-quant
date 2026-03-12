# Volatility Expansion After Compression — Diagnostic Summary

## Strategy hypothesis

When a session is unusually compressed, the next major session may expand in range.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Diagnostic methodology

Script:

- `scripts/analyze_volatility_expansion_after_compression.py`

Session windows:

- Asia: `00:00-07:00 UTC`
- London: `07:00-13:00 UTC`
- NY: `13:00-21:00 UTC`

Per session row:

1. Compute session range (`session_high - session_low`)
2. Mark compressed rows using `session_range <= p25(session_range)`
3. Compare compressed row range with next same-day session range
4. Compute `expansion_ratio = next_session_range / session_range`
5. Mark expansion when `expansion_ratio > 1.0`

## Summary results

- `rows_analyzed`: `5461`
- `compressed_frequency`: `0.2509`
- `compressed_rows_with_next_session`: `1179`
- `expansion_probability_after_compression`: `0.9288`
- `median_expansion_ratio_after_compression`: `2.0226`
- `p75_expansion_ratio_after_compression`: `2.7227`

## Interpretation

- Compressed sessions occur often enough for research (`~25%` by construction).
- Next-session expansion after compression is very frequent (`~92.9%`).
- Expansion magnitude is material (median next session about `2.0x` compressed range).
- This supports the regime hypothesis as a potentially useful filter for later strategy design.

## Conclusion

Verdict: `promising_enough_to_implement_mvp`

Classification: diagnostic complete, promising enough for MVP research implementation.

## Outputs

- `outputs/volatility_expansion_after_compression_diagnostic/summary.json`
- `outputs/volatility_expansion_after_compression_diagnostic/daily_metrics.csv`
- `outputs/volatility_expansion_after_compression_diagnostic/distribution.csv`
