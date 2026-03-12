# Double Impulse Exhaustion — Diagnostic Summary

## Strategy hypothesis

Two strong directional impulses in the same direction within a short session window may indicate
exhaustion and increase reversal probability.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_double_impulse_exhaustion.py`

Setup:

- session window: `13:00-16:00 UTC`
- impulse threshold: `abs(bar close-open) >= 0.8 * ATR(14)`
- double impulse: two same-direction impulses within `8` bars
- reversal horizon: `8` bars after second impulse
- normalization: reversal/adverse move by second impulse size

## Summary results

- `days_analyzed`: `1817`
- `double_impulse_frequency`: `0.6654`
- `bullish_double_impulse_frequency`: `0.4839`
- `bearish_double_impulse_frequency`: `0.5161`
- `reversal_probability`: `0.4743`
- `median_reversal_ratio`: `0.8122`
- `p75_reversal_ratio`: `1.5220`
- `median_adverse_move_ratio`: `0.8661`

## Interpretation

- Double-impulse events occur frequently with this thresholding.
- Reversal probability is below 50%.
- Median adverse move is larger than median reversal move.
- The tested exhaustion framing does not show a robust reversal edge.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/double_impulse_exhaustion_diagnostic/summary.json`
- `outputs/double_impulse_exhaustion_diagnostic/daily_metrics.csv`
- `outputs/double_impulse_exhaustion_diagnostic/distribution.csv`
