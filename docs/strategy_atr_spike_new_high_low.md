# ATR Spike + New High/Low MVP

## Hypothesis

When volatility spikes (`ATR / median_ATR`) at the same time as a 20-bar breakout, continuation may be strong enough for a simple directional strategy.

## Event Definition

- ATR spike:
  - `ATR(14) / rolling_median_ATR(40) >= 1.5`
- Breakout:
  - `new_high_20` or `new_low_20`

## Entry Logic

- ATR spike + `new_high_20` -> `long`
- ATR spike + `new_low_20` -> `short`
- Execution remains next-bar open through existing simulator.

## Exit Logic (MVP)

- Stop loss: `1.0 * ATR`
- Take profit: `1.5 * ATR`
- Time exit: `max_holding_bars = 8`

## Dataset

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Smoke Backtest Result

Output folder:

- `outputs/atr_spike_new_high_low_smoke/`

Metrics:

- total_trades: `5401`
- win_rate: `0.3918`
- net_pnl: `-0.38176`
- profit_factor: `0.8615`
- max_drawdown: `0.41678`

## Initial Interpretation

The setup generates many signals but remains clearly unprofitable with large drawdown under this simple breakout-following formulation.

## Current Status

- `mvp_implemented_rejected`
