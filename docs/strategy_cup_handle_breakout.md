# Cup and Handle Breakout — Diagnostic Summary

## Strategy hypothesis

A rounded cup base followed by a shallow handle pullback and breakout may continue in the breakout direction.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_cup_handle_breakout.py`

Mechanical approximation:

- analysis window: `07:00-17:00 UTC`
- identify cup rims from swing highs
- cup low must sit between rims and define positive cup depth
- cup depth >= `0.8 * ATR(14)`
- left/right rims within `0.4 * ATR(14)`
- handle depth <= `0.5 * cup_depth` within `6` bars after right rim
- breakout confirmation: bar close above resistance
- post-break follow-through/adverse measured over next `8` bars
- normalize by cup depth

## Summary results

- `days_analyzed`: `1817`
- `pattern_frequency`: `0.1596`
- `breakout_success_probability`: `0.5621`
- `median_breakout_follow_through_ratio`: `0.3367`
- `median_adverse_move_ratio`: `0.2645`

## Interpretation

- Pattern events are selective (~16% of days), which is acceptable.
- Breakout win probability is modestly above random.
- Median follow-through is only slightly larger than median adverse move.
- The asymmetry is too weak for a strong standalone breakout edge.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/cup_handle_breakout_diagnostic/summary.json`
- `outputs/cup_handle_breakout_diagnostic/daily_metrics.csv`
- `outputs/cup_handle_breakout_diagnostic/distribution.csv`
