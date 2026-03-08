from __future__ import annotations

import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator


def test_same_bar_tp_and_sl_resolves_to_stop_loss() -> None:
    config = ExecutionConfig(
        mode="bar",
        fill_on_next_open=True,
        ambiguity_mode="conservative",
        market_slippage_pips=0.0,
        stop_slippage_pips=0.0,
        fee_per_trade=0.0,
        pip_size=0.0001,
        max_positions_per_symbol=1,
        flatten_intraday=False,
        flatten_time_utc="21:45",
    )
    simulator = ExecutionSimulator(config)

    order = Order(
        symbol="EURUSD",
        timeframe="15m",
        side="long",
        signal_time=pd.Timestamp("2024-01-02 07:00:00", tz="UTC"),
        entry_reference=1.10000,
        stop_loss=1.09900,
        take_profit=1.10150,
        max_holding_bars=12,
    )
    simulator.submit_order(order)

    fill_bar = pd.Series(
        {
            "timestamp": pd.Timestamp("2024-01-02 07:15:00", tz="UTC"),
            "ask_open": 1.10000,
            "bid_open": 1.09990,
            "bid_low": 1.09920,
            "bid_high": 1.10080,
            "ask_low": 1.09930,
            "ask_high": 1.10090,
            "bid_close": 1.10010,
            "ask_close": 1.10020,
        }
    )
    simulator.process_bar(fill_bar)

    ambiguous_bar = pd.Series(
        {
            "timestamp": pd.Timestamp("2024-01-02 07:30:00", tz="UTC"),
            "ask_open": 1.10010,
            "bid_open": 1.10000,
            "bid_low": 1.09890,
            "bid_high": 1.10160,
            "ask_low": 1.09900,
            "ask_high": 1.10170,
            "bid_close": 1.10020,
            "ask_close": 1.10030,
        }
    )
    simulator.process_bar(ambiguous_bar)

    trades = simulator.get_trades_df()
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "stop_loss"
