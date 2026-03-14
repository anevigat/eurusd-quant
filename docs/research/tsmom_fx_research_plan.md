# FX Trend / Momentum Research Plan

## Hypothesis

Medium-horizon FX trend and time-series momentum strategies may be more robust than many short-horizon intraday reversal ideas and may add a genuinely different source of returns to the repo.

## Market Intuition

Trend and time-series momentum are defensible in FX because:

- macro and rate differentials can persist for months
- position adjustment and hedging flows often unfold gradually
- breakout and return-sign rules can capture directional persistence without relying on fragile intraday microstructure patterns

This is materially different from the repo's dominant event and reversal research, which is concentrated in intraday session transitions, failed breakouts, and short-horizon mean reversion.

## Variants In Scope

This phase intentionally tests only three simple, interpretable variants:

1. `tsmom_ma_cross`
2. `tsmom_donchian`
3. `tsmom_return_sign`

No ML, no large parameter zoo, and no rescue filters were added.

## Exact Rule Definitions

### MA crossover

- long when `fast_ma > slow_ma`
- short when `fast_ma < slow_ma`
- flat when equal
- exit on regime change
- optional ATR stop
- optional ATR trailing stop

### Donchian breakout

- long when close breaks above the highest high of the prior `N` bars
- short when close breaks below the lowest low of the prior `N` bars
- exit on opposite breakout
- optional ATR stop
- optional ATR trailing stop

### Return-sign / threshold momentum

- compute trailing return over a fixed lookback window
- long when return exceeds a positive threshold
- short when return is below the symmetric negative threshold
- flat otherwise
- exit on opposite signal or flat threshold
- optional ATR stop
- optional ATR trailing stop

## Parameters Tested

### `tsmom_ma_cross`

- `fast_window`: `10`, `20`, `50`
- `slow_window`: `50`, `100`, `200`
- `atr_stop_multiple`: `off`, `1.5`, `2.0`
- `trailing_stop`: `false`, `true`

### `tsmom_donchian`

- `breakout_window`: `20`, `55`, `100`
- `atr_stop_multiple`: `off`, `1.5`, `2.0`
- `trailing_stop`: `false`, `true`

### `tsmom_return_sign`

- `lookback_window`: `20`, `60`, `120`
- `return_threshold`: `0.0`, `0.005`
- `atr_stop_multiple`: `off`, `1.5`, `2.0`
- `trailing_stop`: `false`, `true`

## Datasets / Timeframes

- primary dataset: `data/bars/1d/eurusd_bars_1d_2018_2024.parquet`
- cross-pair spot check: `data/bars/1d/gbpusd_bars_1d_2018_2024.parquet`
- source bars were aggregated from existing 15m session-labeled bars using `scripts/prepare_higher_timeframe_bars.py`

Daily bars were used first because they fit the current architecture cleanly and avoid forcing medium-horizon trend logic onto M15 execution assumptions. The strategy code remains compatible with `4h`, but this phase's research runs are daily-first.

## Validation Plan

1. smoke backtest one config per variant
2. run a small in-sample sweep per variant
3. feed the top config from each sweep into the Phase 1 walk-forward pipeline
4. run a limited cross-pair spot check on the strongest one or two EURUSD candidates

## Failure Modes / Overfitting Risks

- low trade counts, especially for long-window breakout rules
- one regime or one year dominating total PnL
- relying on a single pair when broader FX confirmation is weak or unavailable
- drawdown remaining too large even when profit factor is above 1
- adding too many filters to rescue weak trend variants instead of rejecting them

## Scope Limits

- no portfolio logic
- no paper-trading logic
- no ML
- no aggressive optimization
- no claim that any variant is paper-trade ready without stronger Phase 1 evidence
