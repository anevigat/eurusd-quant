# Trend Exhaustion Reversal — Diagnostic Summary

## Strategy hypothesis

Strong directional impulses may exhaust and reverse after momentum slowdown plus structure break.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_trend_exhaustion_reversal.py`

Mechanical definition:

- analysis window: `07:00-17:00 UTC`
- impulse bar: body >= `1.5 * ATR(14)`
- slowdown: next bar body <= `0.4 * impulse_body`
- structure break within `4` bars:
  - bullish impulse: close below impulse low
  - bearish impulse: close above impulse high
- measure reversal/adverse over next `8` bars after break
- normalize by impulse body

## Summary results

- `days_analyzed`: `1817`
- `exhaustion_event_frequency`: `0.0908`
- `reversal_probability`: `0.5515`
- `median_reversal_ratio`: `1.0747`
- `median_adverse_move_ratio`: `0.8231`

## Interpretation

- Events are selective (~9.1% of days), avoiding the over-trigger problem.
- Reversal probability is above random.
- Median reversal ratio exceeds median adverse ratio.
- This structure shows enough asymmetry to justify MVP-level follow-up.

## Conclusion

Verdict: `promising_enough_to_implement_mvp`

Final status: diagnostic complete, promising for MVP implementation research.

## Outputs

- `outputs/trend_exhaustion_reversal_diagnostic/summary.json`
- `outputs/trend_exhaustion_reversal_diagnostic/daily_metrics.csv`
- `outputs/trend_exhaustion_reversal_diagnostic/distribution.csv`

## MVP Implementation and Initial Backtest

MVP rules implemented:

- strong directional impulse over recent `4` bars
- impulse magnitude threshold: `>= 1.5 * ATR(14)`
- exhaustion confirmation:
  - up impulse -> bearish close below prior bar low -> short
  - down impulse -> bullish close above prior bar high -> long
- next-bar execution via existing simulator
- exits:
  - stop: `1.0 * ATR`
  - target: `1.0 * ATR`
  - time exit: `6` bars

Smoke run:

- dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- output: `outputs/trend_exhaustion_reversal_smoke/`
- `total_trades`: `5734`
- `win_rate`: `0.4409`
- `net_pnl`: `-0.4293`
- `expectancy`: `-7.49e-05`
- `profit_factor`: `0.7850`
- `max_drawdown`: `0.4421`

Interpretation:

- despite strong diagnostic asymmetry, this naive tradable formulation over-trades and is structurally unprofitable.
- payoff symmetry with costs and noise leads to clear edge decay in implementation form.

Current status: `mvp_implemented_rejected`
