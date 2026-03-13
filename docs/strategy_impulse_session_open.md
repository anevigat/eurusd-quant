# Impulse Session-Open MVP

## Hypothesis

A sufficiently strong short-horizon ATR impulse occurring around major session transitions (London open or New York open) may continue directionally over the next bars.

## Event Definition

- Impulse strength over last `N` bars:
  - `abs(close_now - close_n_bars_ago) / ATR(14)`
- Trigger threshold:
  - `impulse_strength_atr >= 1.5`
- Session-open windows:
  - London: `06:45-07:15 UTC`
  - New York: `12:45-13:15 UTC`

## Entry Logic

- If strong impulse is upward in open window -> `long`
- If strong impulse is downward in open window -> `short`
- Entry is generated on bar close and executed next-bar open by existing simulator.

## Exit Logic (MVP)

- Stop loss: `1.0 * ATR`
- Take profit: `1.5 * ATR`
- Time exit: `max_holding_bars = 8`

## Dataset

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Smoke Backtest Result

Output folder:

- `outputs/impulse_session_open_smoke/`

Metrics:

- total_trades: `1137`
- win_rate: `0.3562`
- net_pnl: `-0.08895`
- profit_factor: `0.8040`
- max_drawdown: `0.09470`

## Initial Interpretation

The setup generated many trades but was materially unprofitable in this simple continuation formulation. The edge seen in combination analysis does not translate directly into a profitable standalone MVP under this entry/exit design.

## Current Status

- `mvp_implemented_rejected`
