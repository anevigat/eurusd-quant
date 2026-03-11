# London Pullback Continuation (Refined) — Diagnostic Research Summary

## 1. Strategy hypothesis

Refined hypothesis:

- London open can produce strong directional impulses
- after the initial impulse, price may pull back shallow-to-moderate amounts
- if the impulse is genuine, price should then resume in the original direction

The diagnostic objective was to measure whether this continuation structure is strong enough to justify an MVP implementation.

## 2. Dataset used

- Instrument: EURUSD
- Timeframe: 15m bars
- Dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- Days analyzed: `1817`

## 3. Diagnostic methodology

Implemented in:

- `scripts/analyze_london_pullback_continuation.py`

Windows (`UTC`, `[start, end)`):

- London session context: `07:00-10:00`
- impulse window: `07:00-07:45` (first 3 bars)
- pullback window: `07:45-09:00`
- continuation window: `09:00-10:00`

Daily features:

- `impulse_open`, `impulse_close`, `impulse_high`, `impulse_low`
- `impulse_size = abs(impulse_close - impulse_open)`
- `ATR(14)` from 15m bars (true-range rolling mean)
- `impulse_to_atr_ratio = impulse_size / ATR`
- strong impulse flag: `impulse_size >= 0.7 * ATR`

Directional ratios:

- `pullback_ratio = pullback / impulse_size`
- `continuation_ratio = continuation / impulse_size`

Where pullback/continuation are measured symmetrically for bullish vs bearish impulses.

## 4. Summary results

Core frequencies:

- `strong_impulse_frequency`: `0.6990`
- `bullish_impulse_frequency`: `0.5421`
- `bearish_impulse_frequency`: `0.4568`

Impulse-to-ATR:

- `median_impulse_to_atr_ratio`: `1.2202`
- `p75_impulse_to_atr_ratio`: `1.9600`
- `p90_impulse_to_atr_ratio`: `2.7665`

Pullback ratios:

- `median_pullback_ratio`: `2.0092`
- `p75_pullback_ratio`: `4.7618`
- `p90_pullback_ratio`: `12.6636`

Continuation ratios:

- `median_continuation_ratio`: `1.1077`
- `p75_continuation_ratio`: `3.2675`
- `p90_continuation_ratio`: `8.7412`

Strong-impulse continuation only:

- `strong_impulse_days`: `1270`
- `strong_impulse_median_continuation_ratio`: `0.7860`
- `strong_impulse_p75_continuation_ratio`: `1.9915`
- `strong_impulse_p90_continuation_ratio`: `3.6507`

## 5. Interpretation

Findings:

- strong London impulses are frequent enough to be tradable in principle
- however, pullbacks are typically very deep relative to impulse body size (`median ~2.01x`)
- this indicates the raw impulse body definition is not stable as a continuation anchor
- although continuation is present statistically, it coexists with large adverse pullback behavior

Practical implication:

- the current refined diagnostic does not support a clean continuation setup without additional structural constraints (for example, impulse quality filters or different impulse normalization).

## 6. Conclusion

Classification:

- researched but not promising

Reason:

- strong impulses occur often, but pullback depth is too large relative to the measured impulse body, so the setup is not clean enough for immediate MVP strategy implementation.

## 7. Final status

- diagnostic research completed
- no strategy implementation added
- future work, if revisited, should first refine impulse quality definitions before testing tradable rules

## Outputs

- `outputs/london_pullback_continuation_refined_diagnostic/summary.json`
- `outputs/london_pullback_continuation_refined_diagnostic/daily_metrics.csv`
- `outputs/london_pullback_continuation_refined_diagnostic/distribution.csv`
