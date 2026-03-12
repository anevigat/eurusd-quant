from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.london_open_impulse_fade import (
    LondonOpenImpulseFadeConfig,
    LondonOpenImpulseFadeStrategy,
)


def _config(
    *,
    atr_period: int = 1,
    impulse_bars: int = 2,
    impulse_threshold_atr: float = 1.0,
    stop_atr_multiple: float = 1.0,
    target_atr_multiple: float = 1.0,
    max_holding_bars: int = 6,
    one_trade_per_day: bool = True,
) -> LondonOpenImpulseFadeConfig:
    return LondonOpenImpulseFadeConfig(
        timeframe="15m",
        atr_period=atr_period,
        session_start_utc="07:00",
        session_end_utc="08:00",
        impulse_bars=impulse_bars,
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


def _run_strategy(strategy: LondonOpenImpulseFadeStrategy, bars: list[pd.Series]) -> object:
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    return order


def test_no_signal_when_london_impulse_too_small() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config(impulse_threshold_atr=2.0))
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1003, mid_low=1.0998, mid_close=1.1002),
        _bar("2024-01-02 07:15:00", mid_open=1.1002, mid_high=1.1004, mid_low=1.1000, mid_close=1.1003),
        _bar("2024-01-02 07:30:00", mid_open=1.1003, mid_high=1.1004, mid_low=1.0999, mid_close=1.1000),
    ]
    order = _run_strategy(strategy, bars)
    assert order is None


def test_short_signal_after_strong_upward_impulse_and_bearish_confirmation() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config())
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0998, mid_close=1.1008),
        _bar("2024-01-02 07:15:00", mid_open=1.1008, mid_high=1.1018, mid_low=1.1007, mid_close=1.1015),
        _bar("2024-01-02 07:30:00", mid_open=1.1015, mid_high=1.1010, mid_low=1.1004, mid_close=1.1006),
    ]
    order = _run_strategy(strategy, bars)
    assert order is not None
    assert order.side == "short"


def test_long_signal_after_strong_downward_impulse_and_bullish_confirmation() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config())
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.2050, mid_high=1.2051, mid_low=1.2038, mid_close=1.2042),
        _bar("2024-01-02 07:15:00", mid_open=1.2042, mid_high=1.2043, mid_low=1.2025, mid_close=1.2030),
        _bar("2024-01-02 07:30:00", mid_open=1.2030, mid_high=1.2044, mid_low=1.2029, mid_close=1.2041),
    ]
    order = _run_strategy(strategy, bars)
    assert order is not None
    assert order.side == "long"


def test_no_signal_without_confirmation() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config())
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0998, mid_close=1.1008),
        _bar("2024-01-02 07:15:00", mid_open=1.1008, mid_high=1.1018, mid_low=1.1007, mid_close=1.1015),
        _bar("2024-01-02 07:30:00", mid_open=1.1015, mid_high=1.1019, mid_low=1.1009, mid_close=1.1012),
    ]
    order = _run_strategy(strategy, bars)
    assert order is None


def test_stop_and_target_initialized_correctly() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config())
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0998, mid_close=1.1008),
        _bar("2024-01-02 07:15:00", mid_open=1.1008, mid_high=1.1018, mid_low=1.1007, mid_close=1.1015),
        _bar("2024-01-02 07:30:00", mid_open=1.1015, mid_high=1.1010, mid_low=1.1004, mid_close=1.1006),
    ]
    order = _run_strategy(strategy, bars)
    assert order is not None
    assert order.stop_loss > order.entry_reference
    assert order.take_profit < order.entry_reference
    assert order.max_holding_bars == 6
    assert order.stop_loss == pytest.approx(order.entry_reference + 0.0011)
    assert order.take_profit == pytest.approx(order.entry_reference - 0.0011)


def test_no_signal_outside_london_open_window() -> None:
    strategy = LondonOpenImpulseFadeStrategy(_config())
    bars = [
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0998, mid_close=1.1008),
        _bar("2024-01-02 07:15:00", mid_open=1.1008, mid_high=1.1018, mid_low=1.1007, mid_close=1.1015),
        _bar("2024-01-02 08:00:00", mid_open=1.1015, mid_high=1.1019, mid_low=1.1003, mid_close=1.1004),
    ]
    order = _run_strategy(strategy, bars)
    assert order is None
