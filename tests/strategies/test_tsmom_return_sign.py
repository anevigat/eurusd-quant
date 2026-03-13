from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.execution.models import Position
from eurusd_quant.strategies.tsmom_return_sign import TSMOMReturnSignConfig, TSMOMReturnSignStrategy


def _config(**overrides) -> TSMOMReturnSignConfig:
    data = {
        "timeframe": "1d",
        "lookback_window": 2,
        "return_threshold": 0.01,
        "atr_period": 1,
        "atr_stop_multiple": 1.5,
        "trailing_stop": False,
        "max_holding_bars": 50,
    }
    data.update(overrides)
    return TSMOMReturnSignConfig(**data)


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


def test_negative_threshold_raises() -> None:
    with pytest.raises(ValueError, match="return_threshold"):
        TSMOMReturnSignStrategy(_config(return_threshold=-0.01))


def test_no_signal_before_lookback_window() -> None:
    strategy = TSMOMReturnSignStrategy(_config())
    for bar in [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.01)]:
        strategy.on_bar(bar)
        assert strategy.generate_order(bar, False, False) is None


def test_long_signal_when_return_exceeds_threshold() -> None:
    strategy = TSMOMReturnSignStrategy(_config())
    bars = [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.01), _bar("2024-01-03", 1.03)]
    order = None
    for bar in bars:
        strategy.on_bar(bar)
        order = strategy.generate_order(bar, False, False)

    assert order is not None
    assert order.side == "long"


def test_flat_threshold_exit_behavior() -> None:
    strategy = TSMOMReturnSignStrategy(_config(return_threshold=0.02))
    for bar in [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.02), _bar("2024-01-03", 1.05)]:
        strategy.on_bar(bar)

    position = Position(
        side="long",
        symbol="EURUSD",
        entry_time=pd.Timestamp("2024-01-04", tz="UTC"),
        entry_price=1.05,
        stop_loss=1.0,
        take_profit=float("inf"),
        bars_held=0,
        max_holding_bars=50,
        signal_time=pd.Timestamp("2024-01-03", tz="UTC"),
        entry_slippage_cost=0.0,
        entry_spread_cost=0.0,
    )
    flat_bar = _bar("2024-01-04", 1.01)
    strategy.on_bar(flat_bar)

    assert strategy.should_exit_position(flat_bar, position) is True
