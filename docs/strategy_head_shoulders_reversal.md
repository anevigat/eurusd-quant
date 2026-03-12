# Head and Shoulders Reversal — Diagnostic Summary

## Strategy hypothesis

A head-and-shoulders price structure (or inverse form) followed by neckline break may precede directional reversal.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_head_shoulders_reversal.py`

Mechanical approximation:

- analysis window: `07:00-17:00 UTC`
- detect swing highs/lows
- bearish head-and-shoulders:
  - left shoulder, higher head, right shoulder near left shoulder
  - head lift >= `0.3 * ATR(14)`
  - shoulder difference <= `0.3 * ATR(14)`
  - confirmed by close below neckline
- bullish inverse head-and-shoulders mirrors the same logic
- follow-through/adverse measured for next `8` bars after neckline break
- normalized by pattern height

## Summary results

- `days_analyzed`: `1817`
- `pattern_frequency`: `0.5333`
- `bearish_pattern_frequency`: `0.2587`
- `bullish_pattern_frequency`: `0.2746`
- `reversal_probability`: `0.6398`
- `median_follow_through_R`: `0.7100`
- `median_adverse_move_R`: `0.2844`

## Interpretation

- Pattern events are frequent enough for stable diagnostics.
- Reversal probability is materially above random.
- Median follow-through is well above median adverse move.
- The structural asymmetry is strong enough to justify MVP-level follow-up.

## Conclusion

Verdict: `promising_enough_to_implement_mvp`

Final status: diagnostic complete, promising for MVP implementation research.

## Outputs

- `outputs/head_shoulders_reversal_diagnostic/summary.json`
- `outputs/head_shoulders_reversal_diagnostic/daily_metrics.csv`
- `outputs/head_shoulders_reversal_diagnostic/distribution.csv`
