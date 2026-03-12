from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.trend_exhaustion_reversal import (
    TrendExhaustionReversalConfig,
    TrendExhaustionReversalStrategy,
)


def _config(
    *,
    atr_period: int = 1,
    impulse_lookback_bars: int = 3,
    impulse_threshold_atr: float = 1.5,
    stop_atr_multiple: float = 1.0,
    target_atr_multiple: float = 1.0,
    max_holding_bars: int = 6,
    one_trade_per_day: bool = False,
) -> TrendExhaustionReversalConfig:
    return TrendExhaustionReversalConfig(
        timeframe="15m",
        atr_period=atr_period,
        impulse_lookback_bars=impulse_lookback_bars,
        impulse_threshold_atr=impulse_threshold_atr,
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


def test_no_signal_when_impulse_too_small() -> None:
    strategy = TrendExhaustionReversalStrategy(_config(impulse_threshold_atr=3.0))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1008, mid_low=1.0998, mid_close=1.1004),
        _bar("2024-01-02 00:15:00", mid_open=1.1004, mid_high=1.1010, mid_low=1.1002, mid_close=1.1007),
        _bar("2024-01-02 00:30:00", mid_open=1.1007, mid_high=1.1012, mid_low=1.1005, mid_close=1.1009),
        _bar("2024-01-02 00:45:00", mid_open=1.1009, mid_high=1.1010, mid_low=1.0995, mid_close=1.0997),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is None


def test_short_signal_after_strong_up_impulse_and_bearish_break() -> None:
    strategy = TrendExhaustionReversalStrategy(_config(impulse_threshold_atr=1.2))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0995, mid_close=1.1008),
        _bar("2024-01-02 00:15:00", mid_open=1.1008, mid_high=1.1020, mid_low=1.1007, mid_close=1.1017),
        _bar("2024-01-02 00:30:00", mid_open=1.1017, mid_high=1.1032, mid_low=1.1016, mid_close=1.1028),
        _bar("2024-01-02 00:45:00", mid_open=1.1028, mid_high=1.1029, mid_low=1.1010, mid_close=1.1009),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.side == "short"


def test_long_signal_after_strong_down_impulse_and_bullish_break() -> None:
    strategy = TrendExhaustionReversalStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.2050, mid_high=1.2052, mid_low=1.2038, mid_close=1.2040),
        _bar("2024-01-02 00:15:00", mid_open=1.2040, mid_high=1.2041, mid_low=1.2025, mid_close=1.2028),
        _bar("2024-01-02 00:30:00", mid_open=1.2028, mid_high=1.2029, mid_low=1.2010, mid_close=1.2012),
        _bar("2024-01-02 00:45:00", mid_open=1.2012, mid_high=1.2035, mid_low=1.2011, mid_close=1.2032),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.side == "long"


def test_stop_and_target_initialized_in_correct_direction() -> None:
    strategy = TrendExhaustionReversalStrategy(_config(impulse_threshold_atr=1.2))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0995, mid_close=1.1008),
        _bar("2024-01-02 00:15:00", mid_open=1.1008, mid_high=1.1020, mid_low=1.1007, mid_close=1.1017),
        _bar("2024-01-02 00:30:00", mid_open=1.1017, mid_high=1.1032, mid_low=1.1016, mid_close=1.1028),
        _bar("2024-01-02 00:45:00", mid_open=1.1028, mid_high=1.1029, mid_low=1.1010, mid_close=1.1009),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is not None
    assert order.stop_loss > order.entry_reference
    assert order.take_profit < order.entry_reference
    assert order.max_holding_bars == 6


def test_no_signal_without_exhaustion_confirmation() -> None:
    strategy = TrendExhaustionReversalStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0995, mid_close=1.1008),
        _bar("2024-01-02 00:15:00", mid_open=1.1008, mid_high=1.1020, mid_low=1.1007, mid_close=1.1017),
        _bar("2024-01-02 00:30:00", mid_open=1.1017, mid_high=1.1032, mid_low=1.1016, mid_close=1.1028),
        _bar("2024-01-02 00:45:00", mid_open=1.1028, mid_high=1.1031, mid_low=1.1020, mid_close=1.1022),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is None


def test_no_signal_without_minimum_data_requirements() -> None:
    strategy = TrendExhaustionReversalStrategy(_config(atr_period=3, impulse_lookback_bars=4))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0995, mid_close=1.1008),
        _bar("2024-01-02 00:15:00", mid_open=1.1008, mid_high=1.1020, mid_low=1.1007, mid_close=1.1017),
        _bar("2024-01-02 00:30:00", mid_open=1.1017, mid_high=1.1032, mid_low=1.1016, mid_close=1.1028),
    ]
    for bar in bars:
        assert strategy.generate_order(bar, has_open_position=False, has_pending_order=False) is None
