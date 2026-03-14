from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.execution.models import Position
from eurusd_quant.strategies.tsmom_ma_cross import TSMOMMACrossConfig, TSMOMMACrossStrategy


def _config(**overrides) -> TSMOMMACrossConfig:
    data = {
        "timeframe": "1d",
        "fast_window": 2,
        "slow_window": 3,
        "atr_period": 1,
        "atr_stop_multiple": 1.5,
        "trailing_stop": False,
        "max_holding_bars": 50,
    }
    data.update(overrides)
    return TSMOMMACrossConfig(**data)


def _bar(ts: str, close: float, *, high: float | None = None, low: float | None = None) -> pd.Series:
    high = close if high is None else high
    low = close if low is None else low
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "symbol": "EURUSD",
            "bid_close": close - 0.0001,
            "ask_close": close + 0.0001,
            "mid_close": close,
            "mid_high": high,
            "mid_low": low,
        }
    )


def test_invalid_windows_raise() -> None:
    with pytest.raises(ValueError, match="slow_window"):
        TSMOMMACrossStrategy(_config(slow_window=2))


def test_no_signal_before_slow_window_history() -> None:
    strategy = TSMOMMACrossStrategy(_config())
    for bar in [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.1)]:
        strategy.on_bar(bar)
        assert strategy.generate_order(bar, False, False) is None


def test_long_signal_when_fast_ma_above_slow_ma() -> None:
    strategy = TSMOMMACrossStrategy(_config())
    bars = [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.1), _bar("2024-01-03", 1.2)]
    order = None
    for bar in bars:
        strategy.on_bar(bar)
        order = strategy.generate_order(bar, False, False)

    assert order is not None
    assert order.side == "long"
    assert order.timeframe == "1d"


def test_equal_mas_produce_flat_signal() -> None:
    strategy = TSMOMMACrossStrategy(_config())
    bars = [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.0), _bar("2024-01-03", 1.0)]
    order = None
    for bar in bars:
        strategy.on_bar(bar)
        order = strategy.generate_order(bar, False, False)

    assert order is None


def test_opposite_crossover_requests_exit() -> None:
    strategy = TSMOMMACrossStrategy(_config())
    for bar in [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.1), _bar("2024-01-03", 1.2)]:
        strategy.on_bar(bar)

    position = Position(
        side="long",
        symbol="EURUSD",
        entry_time=pd.Timestamp("2024-01-04", tz="UTC"),
        entry_price=1.2,
        stop_loss=1.0,
        take_profit=float("inf"),
        bars_held=0,
        max_holding_bars=50,
        signal_time=pd.Timestamp("2024-01-03", tz="UTC"),
        entry_slippage_cost=0.0,
        entry_spread_cost=0.0,
    )
    for bar in [_bar("2024-01-04", 1.0), _bar("2024-01-05", 0.9)]:
        strategy.on_bar(bar)

    assert strategy.should_exit_position(_bar("2024-01-05", 0.9), position) is True
