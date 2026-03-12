# Break-Retest Continuation — Diagnostic Summary

## Strategy hypothesis

After a session range break, a retest of the broken level may offer cleaner continuation behavior than raw breakout entries.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1822` days

## Diagnostic methodology

Script:

- `scripts/analyze_break_retest_continuation.py`

Windows:

- Reference range: `00:00-07:00 UTC`
- Break/retest analysis: `07:00-10:00 UTC`

Per day:

1. Build Asian range (`asian_high`, `asian_low`, `asian_range`)
2. Detect first confirmed breakout by close outside range
3. Detect retest of broken level in the same analysis window
4. Measure post-retest follow-through vs adverse move
5. Normalize both by Asian range (`R`)

## Summary results

- `days_analyzed`: `1822`
- `breakout_frequency`: `0.8194`
- `retest_frequency_on_breakouts`: `0.7696`
- `continuation_probability_after_retest`: `0.5057`
- `median_follow_through_R_after_retest`: `0.3938`
- `median_adverse_move_R_after_retest`: `0.3817`
- `p75_follow_through_R_after_retest`: `0.7107`
- `p90_follow_through_R_after_retest`: `1.1360`

## Interpretation

- Breakouts and retests are frequent, so the structure is common.
- Continuation probability after retest is close to random (`~50.6%`).
- Median follow-through is only slightly above median adverse move.
- This does not show enough asymmetry for a robust standalone continuation edge.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation in current form.

## Outputs

- `outputs/break_retest_continuation_diagnostic/summary.json`
- `outputs/break_retest_continuation_diagnostic/daily_metrics.csv`
- `outputs/break_retest_continuation_diagnostic/distribution.csv`
