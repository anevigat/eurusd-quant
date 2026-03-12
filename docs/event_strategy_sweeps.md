# Event Strategy Parameter Sweeps

## Purpose

This framework runs large parameter grids for event-driven strategy templates without creating a new strategy file per variant.

It is a research/discovery tool to map where edges may exist before committing to dedicated MVP strategy implementations.

## Template strategy in v1

Script:

- `scripts/run_event_strategy_sweep.py`

Template:

- impulse-reversion (fade large directional impulse)

Event definition:

- impulse over `impulse_bars`:
  - `abs(close_now - close_n_bars_ago) / ATR(14)`
- trigger when impulse strength is at least `impulse_threshold_atr`

Entry:

- fade impulse direction
- optional delay via `entry_delay_bars`

Session filter:

- `none`
- `london` (`07:00-12:00 UTC`)
- `new_york` (`13:00-17:00 UTC`)

Exit:

- stop: `stop_atr * ATR`
- target: `target_atr * ATR`
- time exit: `max_hold_bars`

Execution uses existing backtest components:

- `ExecutionSimulator`
- existing fills/slippage/spread/fees from `config/execution.yaml`
- existing metrics from `eurusd_quant.analytics.metrics`

## Parameter ranges (v1)

- `impulse_bars`: `[1, 2, 3, 4]`
- `impulse_threshold_atr`: `[0.8, 1.0, 1.2, 1.5]`
- `entry_delay_bars`: `[0, 1, 2]`
- `session_filter`: `["none", "london", "new_york"]`
- `stop_atr`: `[0.8, 1.0, 1.2]`
- `target_atr`: `[0.8, 1.0, 1.2]`
- `max_hold_bars`: `[4, 6, 8]`

Full Cartesian grid size is `3888` configs.

For practical runtime, the script defaults to a deterministic subset (`--max-configs 360`). Use `--max-configs 0` to run the full grid.

## Ranking logic

Per config metrics include:

- `total_trades`
- `win_rate`
- `net_pnl`
- `profit_factor`
- `max_drawdown`
- `expectancy`

Ranking score:

- `score = profit_factor * log(total_trades)`

Ranking filter:

- only configs with `total_trades >= min_trades` (default `100`) receive a score

## Outputs

Under `outputs/event_strategy_sweeps/`:

- `experiment_results.csv` (all executed configs + metrics + score)
- `top_configs.csv` (top 20 ranked configs)
- `summary.json` (run metadata and best config)

## How to interpret results

- Positive `net_pnl` with `profit_factor > 1` is necessary but not sufficient.
- Favor configs with both reasonable score and meaningful sample size.
- Very high PF with low trade count should be treated as unstable.
- Use top buckets as hypothesis generators for next strategy iteration, not final validation.

## Future extensions

- additional templates (breakout continuation, breakout failure, session transitions)
- multi-objective ranking (PF, drawdown, expectancy)
- walk-forward sweep mode
- cross-pair sweep mode
- tighter robustness filters (slippage/spread stress overlays)
