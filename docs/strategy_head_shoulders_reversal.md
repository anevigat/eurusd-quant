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

## MVP Implementation and Initial Backtest

MVP rules implemented:

- objective head-and-shoulders / inverse head-and-shoulders structure from swing highs/lows
- shoulders similarity tolerance: `0.5 * ATR(14)`
- minimum head excess: `0.3 * ATR(14)`
- bearish trigger: close below neckline -> short
- bullish trigger: close above neckline -> long
- next-bar execution via existing simulator
- exits:
  - stop: `1.0 * ATR`
  - target: `1.5 * ATR`
  - time exit: `8` bars

Smoke run:

- dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- output: `outputs/head_shoulders_reversal_smoke/`
- `total_trades`: `13066`
- `win_rate`: `0.3676`
- `net_pnl`: `-0.8713`
- `expectancy`: `-6.67e-05`
- `profit_factor`: `0.8172`
- `max_drawdown`: `0.8857`

Interpretation:

- the diagnostic structure does not survive direct tradable implementation with this naive trigger/exit setup.
- trade count is very high and noise dominates; resulting drawdown is not acceptable.

Current status: `mvp_implemented_rejected`
