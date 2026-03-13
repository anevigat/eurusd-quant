# VWAP Session-Open Reversion MVP

## Hypothesis

Around session opens, large ATR-normalized deviations from intraday VWAP may mean-revert back toward VWAP.

## Event Definition

- VWAP proxy:
  - cumulative intraday average of typical price `(high + low + close) / 3` from 00:00 UTC
- Trigger:
  - `abs(mid_close - vwap_proxy) / ATR(14) >= 2.5`
- Open windows:
  - London: `06:45-07:15 UTC`
  - New York: `12:45-13:15 UTC`

## Entry Logic

Mean reversion:

- Positive deviation (price above VWAP) -> `short`
- Negative deviation (price below VWAP) -> `long`

## Exit Logic (MVP)

- Take profit: `session VWAP proxy`
- Stop loss: `1.2 * ATR`
- Time exit: `max_holding_bars = 8`

## Dataset

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Smoke Backtest Result

Output folder:

- `outputs/vwap_session_open_smoke/`

Metrics:

- total_trades: `1099`
- win_rate: `0.3258`
- net_pnl: `-0.02779`
- profit_factor: `0.9527`
- max_drawdown: `0.04886`

## Initial Interpretation

This MVP is closer to break-even than the other two event-combination MVPs, but still unprofitable in current form (PF below 1 with negative net PnL). Additional filtering would be required before considering promotion.

## Current Status

- `mvp_implemented_rejected`
