from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.compression_breakout import (
    CompressionBreakoutConfig,
    CompressionBreakoutStrategy,
)


def _config(
    *,
    atr_period: int = 1,
    compression_median_lookback_bars: int = 3,
    compression_breakout_lookback_bars: int = 3,
    compression_threshold: float = 3.0,
    stop_atr_multiple: float = 1.0,
    target_atr_multiple: float = 1.5,
    max_holding_bars: int = 8,
    one_trade_per_day: bool = False,
) -> CompressionBreakoutConfig:
    return CompressionBreakoutConfig(
        timeframe="15m",
        atr_period=atr_period,
        compression_median_lookback_bars=compression_median_lookback_bars,
        compression_breakout_lookback_bars=compression_breakout_lookback_bars,
        compression_threshold=compression_threshold,
        stop_atr_multiple=stop_atr_multiple,
        target_atr_multiple=target_atr_multiple,
        max_holding_bars=max_holding_bars,
        one_trade_per_day=one_trade_per_day,
    )


def _bar(
    ts: str,
    *,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
    spread: float = 0.0001,
    symbol: str = "EURUSD",
) -> pd.Series:
    half = spread / 2.0
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "symbol": symbol,
            "mid_open": mid_open,
            "mid_high": mid_high,
            "mid_low": mid_low,
            "mid_close": mid_close,
            "bid_close": mid_close - half,
            "ask_close": mid_close + half,
        }
    )


def test_no_signal_when_not_compressed() -> None:
    strategy = CompressionBreakoutStrategy(_config(compression_threshold=0.8))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.1000, mid_close=1.1001),
        _bar("2024-01-02 00:15:00", mid_open=1.1001, mid_high=1.1004, mid_low=1.1002, mid_close=1.1003),
        _bar("2024-01-02 00:30:00", mid_open=1.1003, mid_high=1.1006, mid_low=1.1004, mid_close=1.1005),
        _bar("2024-01-02 00:45:00", mid_open=1.1005, mid_high=1.1014, mid_low=1.1000, mid_close=1.1013),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is None


def test_long_signal_when_compressed_breaks_above_range() -> None:
    strategy = CompressionBreakoutStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.1000, mid_close=1.1001),
        _bar("2024-01-02 00:15:00", mid_open=1.1001, mid_high=1.1003, mid_low=1.1001, mid_close=1.1002),
        _bar("2024-01-02 00:30:00", mid_open=1.1002, mid_high=1.1004, mid_low=1.1002, mid_close=1.1003),
        _bar("2024-01-02 00:45:00", mid_open=1.1003, mid_high=1.1006, mid_low=1.1003, mid_close=1.10055),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.side == "long"


def test_short_signal_when_compressed_breaks_below_range() -> None:
    strategy = CompressionBreakoutStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.2000, mid_high=1.2002, mid_low=1.2000, mid_close=1.2001),
        _bar("2024-01-02 00:15:00", mid_open=1.2001, mid_high=1.2003, mid_low=1.2001, mid_close=1.2002),
        _bar("2024-01-02 00:30:00", mid_open=1.2002, mid_high=1.2004, mid_low=1.2002, mid_close=1.2003),
        _bar("2024-01-02 00:45:00", mid_open=1.2003, mid_high=1.2003, mid_low=1.1998, mid_close=1.19985),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.side == "short"


def test_stop_and_target_initialized_correctly() -> None:
    strategy = CompressionBreakoutStrategy(_config(stop_atr_multiple=1.0, target_atr_multiple=1.5))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.1000, mid_close=1.1001),
        _bar("2024-01-02 00:15:00", mid_open=1.1001, mid_high=1.1003, mid_low=1.1001, mid_close=1.1002),
        _bar("2024-01-02 00:30:00", mid_open=1.1002, mid_high=1.1004, mid_low=1.1002, mid_close=1.1003),
        _bar("2024-01-02 00:45:00", mid_open=1.1003, mid_high=1.1006, mid_low=1.1003, mid_close=1.10055),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.stop_loss < order.entry_reference
    assert order.take_profit > order.entry_reference
    assert order.max_holding_bars == 8
    # ATR(period=1) at signal bar ~ 0.0003
    assert order.stop_loss == pytest.approx(order.entry_reference - 0.0003)
    assert order.take_profit == pytest.approx(order.entry_reference + 0.00045)


def test_no_signal_if_breakout_not_occurring() -> None:
    strategy = CompressionBreakoutStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.1000, mid_close=1.1001),
        _bar("2024-01-02 00:15:00", mid_open=1.1001, mid_high=1.1003, mid_low=1.1001, mid_close=1.1002),
        _bar("2024-01-02 00:30:00", mid_open=1.1002, mid_high=1.1004, mid_low=1.1002, mid_close=1.1003),
        _bar("2024-01-02 00:45:00", mid_open=1.1003, mid_high=1.10035, mid_low=1.10025, mid_close=1.10030),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is None
