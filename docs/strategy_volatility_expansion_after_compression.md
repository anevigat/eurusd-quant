# Volatility Expansion After Compression — Diagnostic Summary

## Strategy hypothesis

When a session is unusually compressed, the next major session may expand in range.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Diagnostic methodology

Script:

- `scripts/analyze_volatility_expansion_after_compression.py`

Session windows:

- Asia: `00:00-07:00 UTC`
- London: `07:00-13:00 UTC`
- NY: `13:00-21:00 UTC`

Per session row:

1. Compute session range (`session_high - session_low`)
2. Mark compressed rows using `session_range <= p25(session_range)`
3. Compare compressed row range with next same-day session range
4. Compute `expansion_ratio = next_session_range / session_range`
5. Mark expansion when `expansion_ratio > 1.0`

## Summary results

- `rows_analyzed`: `5461`
- `compressed_frequency`: `0.2509`
- `compressed_rows_with_next_session`: `1179`
- `expansion_probability_after_compression`: `0.9288`
- `median_expansion_ratio_after_compression`: `2.0226`
- `p75_expansion_ratio_after_compression`: `2.7227`

## Interpretation

- Compressed sessions occur often enough for research (`~25%` by construction).
- Next-session expansion after compression is very frequent (`~92.9%`).
- Expansion magnitude is material (median next session about `2.0x` compressed range).
- This supports the regime hypothesis as a potentially useful filter for later strategy design.

## Diagnostic Conclusion

Verdict: `promising_enough_to_implement_mvp`

Classification: diagnostic complete, promising enough for MVP research implementation.

## MVP Implementation and Results

### 1. MVP design

Implemented MVP:

- `src/eurusd_quant/strategies/volatility_expansion_after_compression.py`
- runner key: `volatility_expansion_after_compression`

Rules:

1. ATR(14) compression state vs rolling median ATR (40 bars)
2. compressed when `current_atr <= 0.75 * rolling_median_atr`
3. arm breakout range from compression window high/low
4. enter on close breakout (long above range high, short below range low)
5. next-bar execution via existing simulator
6. stop `1.0 * ATR`, target `1.5 * ATR`, time exit `8` bars

### 2. Backtest dataset

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

### 3. Smoke backtest results

- `total_trades`: `1956`
- `win_rate`: `0.3569`
- `net_pnl`: `-0.1594`
- `profit_factor`: `0.7658`
- `max_drawdown`: `0.1700`

### 4. Interpretation

Although the diagnostic suggested that expansion after compression occurs frequently, the
simple MVP trading implementation was not profitable.

The strategy generated a large number of trades, but:

- win rate was low
- profit factor was materially below 1
- drawdown was high

This indicates that the observed expansion behavior does not translate into a robust tradable
edge with the naive breakout formulation tested here.

### 5. Final conclusion

Final status: `researched_but_not_promising` (MVP tested)

- the diagnostic identified real market behavior
- the tested strategy structure was not strong enough
- this exact formulation should not be pursued further without a materially different hypothesis

### 6. Output references

Diagnostic outputs:

- `outputs/volatility_expansion_after_compression_diagnostic/summary.json`
- `outputs/volatility_expansion_after_compression_diagnostic/daily_metrics.csv`
- `outputs/volatility_expansion_after_compression_diagnostic/distribution.csv`

MVP smoke outputs:

- `outputs/volatility_expansion_after_compression_smoke/`
- `outputs/volatility_expansion_after_compression_smoke/metrics.json`
- `outputs/volatility_expansion_after_compression_smoke/trades.parquet`

## Alternative Compression Breakout MVP

### 1. Compression rule and trigger

Alternative MVP implementation:

- strategy key: `compression_breakout`
- ATR(14) compression ratio:
  - `compression_ratio = ATR(14) / rolling_median_ATR(40)`
- compressed when `compression_ratio <= 0.60`
- breakout reference window: prior `20` bars
- long trigger: close above prior 20-bar high while compressed
- short trigger: close below prior 20-bar low while compressed
- next-bar execution via existing simulator

### 2. Exits

- stop: `1.0 * ATR`
- target: `1.5 * ATR`
- time exit: `8` bars

### 3. Smoke metrics

- dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- output: `outputs/compression_breakout_smoke/`
- `total_trades`: `1766`
- `win_rate`: `0.3029`
- `net_pnl`: `-0.1710`
- `expectancy`: `-9.68e-05`
- `profit_factor`: `0.5642`
- `max_drawdown`: `0.1705`

### 4. Interpretation

- This variant remains unprofitable with lower win rate and lower profit factor than the prior volatility-expansion MVP.
- The core compression-expansion observation still does not translate into a robust tradable breakout formulation in this simple design.

### 5. Status

`compression_breakout`: `mvp_implemented_rejected`

## Compression + Breakout Continuation MVP

### 1. Improved breakout logic

Second alternative MVP implementation:

- strategy key: `compression_breakout_continuation`
- compression:
  - `compression_ratio = ATR(14) / rolling_median_ATR(40)`
  - compressed when `compression_ratio <= 0.60`
- breakout window: prior `20` bars
- long trigger:
  - compressed state true
  - close above prior 20-bar high
  - close in top 30% of candle range
- short trigger:
  - compressed state true
  - close below prior 20-bar low
  - close in bottom 30% of candle range
- execution remains next-bar open via existing simulator

### 2. Exits

- stop: `1.0 * ATR`
- target: `1.5 * ATR`
- time exit: `8` bars

### 3. Smoke metrics

- dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- output: `outputs/compression_breakout_continuation_smoke/`
- `total_trades`: `1463`
- `win_rate`: `0.2891`
- `net_pnl`: `-0.1603`
- `expectancy`: `-1.0957e-04`
- `profit_factor`: `0.5218`
- `max_drawdown`: `0.1603`

### 4. Interpretation

- The stronger close-confirmation filter reduced trade count versus the prior compression breakout variant.
- Performance remained clearly negative with very weak profit factor and high drawdown.
- The compression plus structural-breakout continuation formulation still does not show a tradable edge in this MVP form.

### 5. Status

`compression_breakout_continuation`: `mvp_implemented_rejected`
