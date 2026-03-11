# London Opening Range Breakout — Research Summary

## 1. Strategy hypothesis

Classical London breakout hypothesis:

- Asian session builds a range (`00:00-07:00 UTC`)
- London open introduces institutional liquidity
- price breaks the Asian range and continues in breakout direction

This behavior is widely studied, but in practice it is often affected by false breakouts and usually needs additional filters.

## 2. Dataset

Data source:

- EURUSD 15m bars

Dataset used:

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

Sample size:

- `1822` trading days

## 3. Diagnostic methodology

Diagnostic implementation:

- `scripts/analyze_london_range_breakout.py`

Daily calculations:

Asian session (`00:00-07:00 UTC`):

- `asian_high`
- `asian_low`
- `asian_range`

London window (`07:00-10:00 UTC`):

- breakout detection:
  - `break_above_range`
  - `break_below_range`
  - `first_break_direction`

Follow-through metrics:

- `follow_through_R`
- `adverse_move_R`

Where `R = asian_range`.

## 4. Diagnostic results

- `days_analyzed`: `1822`
- `breakout_frequency`: `0.9171`
- `break_above_frequency`: `0.5560`
- `break_below_frequency`: `0.5483`

Follow-through:

- `median_follow_through_R`: `0.4606`
- `p75_follow_through_R`: `0.8728`
- `p90_follow_through_R`: `1.3333`

Adverse move:

- `median_adverse_move_R`: `0.5195`

## 5. Interpretation

Key findings:

- breakouts occur very frequently (~`91.7%` of days)
- continuation after breakout is modest
- median continuation is ~`0.46R`
- median adverse excursion (~`0.52R`) is slightly larger than median continuation

This indicates raw breakout behavior is not strong enough to support a standalone continuation strategy.

## 6. Conclusion

The simple London Opening Range Breakout does not appear to provide a robust standalone edge on EURUSD 15-minute data.

Breakouts are frequent, but continuation is not consistent enough.

Classification:

- researched but not promising

## 7. Possible improvements (future research)

- Asian range compression filter
- volatility regime filter
- first-break confirmation (close outside range)
- trend filter
- breakout retest entry

## 8. Outputs

Diagnostic outputs:

- `outputs/london_range_breakout_diagnostic/summary.json`
- `outputs/london_range_breakout_diagnostic/daily_metrics.csv`
- `outputs/london_range_breakout_diagnostic/range_distribution.csv`

## 9. Final status

- diagnostic research completed
- strategy not implemented
- future work may explore filtered breakout variants
