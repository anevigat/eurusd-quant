# Double Top / Double Bottom Reversal — Diagnostic Summary

## Strategy hypothesis

Markets may reverse after two similar highs or lows followed by a neckline break.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_double_top_bottom.py`

Mechanical approximation:

- analysis window: `07:00-17:00 UTC`
- ATR normalization: `ATR(14)`
- double top:
  - two swing highs within `0.3 * ATR` tolerance
  - pullback depth at least `0.5 * ATR`
  - close below neckline confirms pattern
- double bottom: mirrored rules
- post-break outcome measured over `8` bars:
  - follow-through_R
  - adverse_move_R

## Summary results

- `days_analyzed`: `1817`
- `pattern_frequency`: `0.9697`
- `bullish_pattern_frequency`: `0.4886`
- `bearish_pattern_frequency`: `0.5114`
- `reversal_probability`: `0.5942`
- `median_follow_through_R`: `1.1696`
- `median_adverse_move_R`: `0.6610`

## Interpretation

- The approximation flags patterns on nearly all days, which indicates low selectivity.
- While headline reversal metrics look strong, detection is too permissive to represent a clean
  chart-pattern signal.
- The current mechanical definition is not sufficiently discriminative for robust strategy design.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/double_top_bottom_reversal_diagnostic/summary.json`
- `outputs/double_top_bottom_reversal_diagnostic/daily_metrics.csv`
- `outputs/double_top_bottom_reversal_diagnostic/distribution.csv`
