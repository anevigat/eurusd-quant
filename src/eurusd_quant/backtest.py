from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.registry import build_strategy


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    metrics: dict[str, float | int]


def run_backtest(
    bars: pd.DataFrame,
    strategy_name: str,
    strategy_config: dict[str, Any],
    execution_config: dict[str, Any] | ExecutionConfig,
) -> BacktestResult:
    strategy = build_strategy(strategy_name, strategy_config)
    simulator = ExecutionSimulator(
        execution_config if isinstance(execution_config, ExecutionConfig) else ExecutionConfig.from_dict(execution_config)
    )

    for _, bar in bars.iterrows():
        strategy.on_bar(bar)
        simulator.process_bar(bar)
        if simulator.has_open_position():
            position = simulator.get_open_position()
            if position is not None:
                if strategy.should_exit_position(bar, position):
                    simulator.close_open_position_at_market(bar, exit_reason="signal_exit")
                    position = simulator.get_open_position()
                if position is not None:
                    updated = strategy.update_open_position(bar, position)
                    if updated is not None:
                        simulator.update_open_position_brackets(*updated)
        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)

    if not bars.empty:
        simulator.close_open_position_at_end(bars.iloc[-1])

    trades = simulator.get_trades_df()
    return BacktestResult(trades=trades, metrics=compute_metrics(trades))
