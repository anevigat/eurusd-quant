from __future__ import annotations

import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator


def _config(**overrides: object) -> ExecutionConfig:
    base = {
        "mode": "bar",
        "fill_on_next_open": True,
        "ambiguity_mode": "conservative",
        "market_slippage_pips": 0.1,
        "stop_slippage_pips": 0.2,
        "fee_per_trade": 0.0,
        "pip_size": 0.0001,
        "max_positions_per_symbol": 1,
        "flatten_intraday": False,
        "flatten_time_utc": "21:45",
        "reanchor_brackets_after_fill": False,
    }
    base.update(overrides)
    return ExecutionConfig(**base)


def _bar(
    ts: str,
    *,
    ask_open: float = 1.10010,
    bid_open: float = 1.10000,
    ask_high: float = 1.10030,
    ask_low: float = 1.09990,
    bid_high: float = 1.10020,
    bid_low: float = 1.09980,
    ask_close: float = 1.10015,
    bid_close: float = 1.10005,
) -> pd.Series:
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "ask_open": ask_open,
            "bid_open": bid_open,
            "ask_high": ask_high,
            "ask_low": ask_low,
            "bid_high": bid_high,
            "bid_low": bid_low,
            "ask_close": ask_close,
            "bid_close": bid_close,
        }
    )


def _long_order(max_holding_bars: int = 12) -> Order:
    return Order(
        symbol="EURUSD",
        timeframe="15m",
        side="long",
        signal_time=pd.Timestamp("2024-01-02 07:00:00", tz="UTC"),
        entry_reference=1.10000,
        stop_loss=1.09900,
        take_profit=1.10150,
        max_holding_bars=max_holding_bars,
    )


def test_time_exit_after_max_holding_bars() -> None:
    simulator = ExecutionSimulator(_config(flatten_intraday=False))
    simulator.submit_order(_long_order(max_holding_bars=2))

    simulator.process_bar(_bar("2024-01-02 07:15:00"))
    simulator.process_bar(_bar("2024-01-02 07:30:00"))

    trades = simulator.get_trades_df()
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "time_exit"


def test_flatten_intraday_exits_when_time_is_greater_than_flatten_time() -> None:
    simulator = ExecutionSimulator(_config(flatten_intraday=True, flatten_time_utc="21:45"))
    simulator.submit_order(_long_order(max_holding_bars=50))

    simulator.process_bar(_bar("2024-01-02 21:30:00"))
    simulator.process_bar(_bar("2024-01-02 22:00:00"))

    trades = simulator.get_trades_df()
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "flatten_intraday"


def test_brackets_remain_absolute_after_fill_when_reanchor_disabled() -> None:
    simulator = ExecutionSimulator(_config(market_slippage_pips=0.5, reanchor_brackets_after_fill=False))
    simulator.submit_order(_long_order(max_holding_bars=50))

    simulator.process_bar(_bar("2024-01-02 07:15:00", ask_open=1.10000, bid_open=1.09990))
    simulator.process_bar(
        _bar(
            "2024-01-02 07:30:00",
            bid_low=1.09903,
            bid_high=1.10020,
            ask_low=1.09913,
            ask_high=1.10030,
        )
    )

    assert simulator.has_open_position()
    assert simulator.get_trades_df().empty


def test_trade_output_includes_pips_slippage_and_spread_costs() -> None:
    simulator = ExecutionSimulator(_config(flatten_intraday=True, flatten_time_utc="21:45"))
    simulator.submit_order(_long_order(max_holding_bars=50))

    simulator.process_bar(_bar("2024-01-02 21:30:00", ask_open=1.10020, bid_open=1.10010))
    simulator.process_bar(
        _bar(
            "2024-01-02 22:00:00",
            ask_open=1.10025,
            bid_open=1.10015,
            ask_close=1.10030,
            bid_close=1.10020,
        )
    )

    trades = simulator.get_trades_df()
    assert len(trades) == 1
    row = trades.iloc[0]
    assert "pnl_pips" in trades.columns
    assert "slippage_cost" in trades.columns
    assert "spread_cost" in trades.columns
    assert row["pnl_pips"] == row["net_pnl"] / 0.0001
    assert row["slippage_cost"] > 0.0
    assert row["spread_cost"] > 0.0
