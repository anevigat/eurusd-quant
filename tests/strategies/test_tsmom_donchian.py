from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.execution.models import Position
from eurusd_quant.strategies.tsmom_donchian import TSMOMDonchianConfig, TSMOMDonchianStrategy


def _config(**overrides) -> TSMOMDonchianConfig:
    data = {
        "timeframe": "1d",
        "breakout_window": 3,
        "atr_period": 1,
        "atr_stop_multiple": 1.5,
        "trailing_stop": False,
        "max_holding_bars": 50,
    }
    data.update(overrides)
    return TSMOMDonchianConfig(**data)


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


def test_invalid_breakout_window_raises() -> None:
    with pytest.raises(ValueError, match="breakout_window"):
        TSMOMDonchianStrategy(_config(breakout_window=1))


def test_no_signal_until_prior_window_exists() -> None:
    strategy = TSMOMDonchianStrategy(_config())
    for bar in [_bar("2024-01-01", 1.0), _bar("2024-01-02", 1.1), _bar("2024-01-03", 1.2)]:
        strategy.on_bar(bar)
        assert strategy.generate_order(bar, False, False) is None


def test_long_breakout_uses_prior_highs_only() -> None:
    strategy = TSMOMDonchianStrategy(_config())
    bars = [
        _bar("2024-01-01", 1.00, high=1.00, low=0.99),
        _bar("2024-01-02", 1.05, high=1.05, low=1.00),
        _bar("2024-01-03", 1.10, high=1.10, low=1.02),
        _bar("2024-01-04", 1.12, high=1.13, low=1.05),
    ]
    order = None
    for bar in bars:
        strategy.on_bar(bar)
        order = strategy.generate_order(bar, False, False)

    assert order is not None
    assert order.side == "long"


def test_equal_to_prior_high_is_not_breakout() -> None:
    strategy = TSMOMDonchianStrategy(_config())
    bars = [
        _bar("2024-01-01", 1.00, high=1.00, low=0.99),
        _bar("2024-01-02", 1.05, high=1.05, low=1.00),
        _bar("2024-01-03", 1.10, high=1.10, low=1.02),
        _bar("2024-01-04", 1.10, high=1.10, low=1.05),
    ]
    order = None
    for bar in bars:
        strategy.on_bar(bar)
        order = strategy.generate_order(bar, False, False)

    assert order is None


def test_flat_channel_does_not_force_exit() -> None:
    strategy = TSMOMDonchianStrategy(_config())
    for bar in [
        _bar("2024-01-01", 1.00, high=1.00, low=0.99),
        _bar("2024-01-02", 1.05, high=1.05, low=1.00),
        _bar("2024-01-03", 1.10, high=1.10, low=1.02),
        _bar("2024-01-04", 1.12, high=1.13, low=1.05),
    ]:
        strategy.on_bar(bar)

    position = Position(
        side="long",
        symbol="EURUSD",
        entry_time=pd.Timestamp("2024-01-05", tz="UTC"),
        entry_price=1.12,
        stop_loss=1.0,
        take_profit=float("inf"),
        bars_held=0,
        max_holding_bars=50,
        signal_time=pd.Timestamp("2024-01-04", tz="UTC"),
        entry_slippage_cost=0.0,
        entry_spread_cost=0.0,
    )
    flat_bar = _bar("2024-01-05", 1.08, high=1.09, low=1.06)
    strategy.on_bar(flat_bar)

    assert strategy.should_exit_position(flat_bar, position) is False
