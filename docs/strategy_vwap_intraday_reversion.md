# VWAP Intraday Reversion — Diagnostic Research Summary

## 1. Strategy hypothesis

Hypothesis:

- when price moves far enough away from intraday VWAP, it may mean-revert back toward VWAP later in the session
- larger deviations (in ATR units) should show stronger short-horizon reversion than smaller deviations

This diagnostic focuses on structure only, before any strategy implementation.

## 2. Dataset used

- Instrument: EURUSD
- Timeframe: 15m bars
- Dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## 3. Diagnostic methodology

Implemented in:

- `scripts/analyze_vwap_intraday_reversion.py`

Session scope:

- full day data used for intraday VWAP construction (`00:00-23:45 UTC`)
- active analysis window: `07:00-17:00 UTC` (`[start, end)`)

VWAP method:

- no traded volume is available in standard bars
- used cumulative average of typical price per day as a VWAP proxy:
  - `typical_price = (mid_high + mid_low + mid_close) / 3`
  - intraday VWAP proxy = cumulative mean of typical price from `00:00` onward

Deviation and normalization:

- `deviation = mid_close - intraday_vwap`
- `deviation_atr = deviation / ATR(14)`
- buckets by `abs(deviation_atr)` quantiles:
  - `small_dev <= p50`
  - `medium_dev (p50, p75]`
  - `large_dev (p75, p90]`
  - `extreme_dev > p90`

Reversion measurement:

- lookahead horizons:
  - next 4 bars (1 hour)
  - next 8 bars (2 hours)
- `reversion_ratio = (abs(dev_now) - abs(dev_horizon)) / abs(dev_now)`
  - `> 0`: moved toward VWAP
  - `< 0`: moved further away

## 4. Summary results

Global:

- `bars_analyzed`: `72,696`
- `median_abs_deviation_atr`: `1.6633`
- `p75_abs_deviation_atr`: `2.7902`
- `p90_abs_deviation_atr`: `3.9346`

Bucket medians (4-bar / 8-bar reversion):

- `small_dev`: `-0.4827 / -0.8217`
- `medium_dev`: `0.0726 / 0.0971`
- `large_dev`: `0.0816 / 0.1314`
- `extreme_dev`: `0.0785 / 0.1350`

Sign split medians:

- positive deviations:
  - 4 bars: `-0.0492`
  - 8 bars: `-0.0953`
- negative deviations:
  - 4 bars: `-0.0549`
  - 8 bars: `-0.1045`

## 5. MVP Implementation and Results

### 5.1 MVP strategy design

Implemented MVP logic:

- session window: `07:00-17:00 UTC`
- VWAP proxy: cumulative average of typical price from `00:00`
- entry:
  - long when negative deviation from VWAP crosses threshold
  - short when positive deviation from VWAP crosses threshold
- threshold:
  - `deviation_threshold_atr = 2.8`
- exits:
  - target: partial reversion toward VWAP (`50%` of entry-to-VWAP distance)
  - stop: `1.0 * ATR(14)`
  - time exit: `max_holding_bars = 4`

### 5.2 Backtest dataset

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

### 5.3 Backtest results (smoke run)

- `total_trades`: `1580`
- `win_rate`: `0.4297`
- `net_pnl`: `-0.01617`
- `profit_factor`: `0.9736`
- `max_drawdown`: `0.03188`

## 6. Interpretation

Although the diagnostic stage suggested a mild mean-reversion tendency when price deviates far from VWAP, the MVP strategy itself was not profitable.

With a relatively large sample (`1580` trades), profit factor remained below `1` and net PnL remained negative.

Interpretation:

- the raw VWAP reversion effect appears too weak for a simple implementation
- additional structure is likely required before this idea can become tradable

## 7. Conclusion

Status:

- researched but not promising (current form)

Conclusion:

- VWAP intraday reversion behavior exists directionally in diagnostics
- but the tested MVP design does not translate that into a profitable strategy

Potential future revisit paths:

- volatility regime filters
- session-specific behavior constraints
- liquidity/spread-aware conditions
- stronger deviation thresholds
- alternative exit models

## 8. Outputs

Diagnostic artifacts:

- `outputs/vwap_intraday_reversion_diagnostic/summary.json`
- `outputs/vwap_intraday_reversion_diagnostic/daily_metrics.csv`
- `outputs/vwap_intraday_reversion_diagnostic/distribution.csv`

MVP backtest artifacts:

- `outputs/vwap_intraday_reversion_smoke/metrics.json`
- `outputs/vwap_intraday_reversion_smoke/trades.parquet`

## 9. Final status

- diagnostic research completed
- MVP implementation tested
- current verdict: not promising without additional filtering/structure
