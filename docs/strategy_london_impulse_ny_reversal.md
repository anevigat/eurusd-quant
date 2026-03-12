# London Impulse to NY Reversal — Diagnostic Summary

## Strategy hypothesis

A strong London directional impulse may partially reverse when New York liquidity enters.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` valid days

## Diagnostic methodology

Script:

- `scripts/analyze_london_impulse_ny_reversal.py`

Windows:

- London impulse: `07:00-12:00 UTC`
- NY reversal window: `12:00-16:00 UTC`

Per day:

1. Compute London impulse (`london_close - london_open`)
2. Compute ATR(14) reference at end of London window
3. Label strong impulse when `impulse_size >= 1.0 * ATR`
4. Measure NY reversal and adverse move versus London close
5. Normalize both by London impulse size

## Summary results

- `days_analyzed`: `1817`
- `strong_london_impulse_frequency`: `0.7722`
- `bullish_impulse_frequency`: `0.4825`
- `bearish_impulse_frequency`: `0.5175`
- `median_reversal_ratio`: `0.7828`
- `p75_reversal_ratio`: `1.6914`
- `p90_reversal_ratio`: `3.0594`
- `median_adverse_move_ratio`: `0.8142`

## Interpretation

- Strong London impulses are frequent in this framing.
- NY reversal magnitude is non-trivial, but median adverse move is slightly larger than median reversal.
- The structure does not provide clear asymmetry for a robust standalone reversal edge.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/london_impulse_ny_reversal_diagnostic/summary.json`
- `outputs/london_impulse_ny_reversal_diagnostic/daily_metrics.csv`
- `outputs/london_impulse_ny_reversal_diagnostic/distribution.csv`

## London Open Impulse Fade MVP

### 1. MVP rule definition

Implemented MVP:

- strategy key: `london_open_impulse_fade`
- focus window: `07:00-08:00 UTC`
- impulse setup:
  - first `2` bars after `07:00`
  - `impulse_size_atr = abs(close_impulse_end - open_impulse_start) / ATR(14)`
  - strong impulse when `impulse_size_atr >= 1.0`
- fade confirmation:
  - upward impulse -> short on close crossing below impulse midpoint
  - downward impulse -> long on close crossing above impulse midpoint
- execution: next-bar open via existing simulator

### 2. Exits

- stop: `1.0 * ATR`
- target: `1.0 * ATR`
- time exit: `6` bars

### 3. Smoke metrics

- dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- output: `outputs/london_open_impulse_fade_smoke/`
- `total_trades`: `270`
- `win_rate`: `0.4593`
- `net_pnl`: `-0.01193`
- `expectancy`: `-4.42e-05`
- `profit_factor`: `0.8625`
- `max_drawdown`: `0.01820`

### 4. Interpretation

- The fade setup produced a moderate trade count with relatively balanced win/loss profile.
- Despite this, the strategy remained slightly negative with `profit_factor < 1`.
- In this simple MVP formulation, the London-open impulse fade effect is not strong enough to classify as promising.

### 5. Status

`london_open_impulse_fade`: `mvp_implemented_rejected`
