from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.impulse_session_open import (
    ImpulseSessionOpenConfig,
    ImpulseSessionOpenStrategy,
)


def make_bar(
    ts: str,
    *,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
    spread: float = 0.0001,
) -> pd.Series:
    half = spread / 2.0
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "symbol": "EURUSD",
            "timeframe": "15m",
            "mid_open": mid_open,
            "mid_high": mid_high,
            "mid_low": mid_low,
            "mid_close": mid_close,
            "bid_open": mid_open - half,
            "bid_high": mid_high - half,
            "bid_low": mid_low - half,
            "bid_close": mid_close - half,
            "ask_open": mid_open + half,
            "ask_high": mid_high + half,
            "ask_low": mid_low + half,
            "ask_close": mid_close + half,
            "spread_open": spread,
            "spread_high": spread,
            "spread_low": spread,
            "spread_close": spread,
            "session_label": "other",
        }
    )


def build_strategy() -> ImpulseSessionOpenStrategy:
    config = ImpulseSessionOpenConfig(
        timeframe="15m",
        atr_period=2,
        impulse_bars=2,
        impulse_threshold_atr=1.5,
        london_window_start_utc="06:45",
        london_window_end_utc="07:15",
        new_york_window_start_utc="12:45",
        new_york_window_end_utc="13:15",
        stop_atr_multiple=1.0,
        target_atr_multiple=1.5,
        max_holding_bars=8,
        one_trade_per_day=True,
    )
    return ImpulseSessionOpenStrategy(config)


def run_until_signal(strategy: ImpulseSessionOpenStrategy, bars: list[pd.Series]):
    order = None
    for bar in bars:
        order = strategy.generate_order(
            bar,
            has_open_position=False,
            has_pending_order=False,
        )
    return order


def test_no_signal_when_impulse_below_threshold() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1002, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 07:00", mid_open=1.1001, mid_high=1.1003, mid_low=1.1000, mid_close=1.1002),
    ]
    order = run_until_signal(strategy, bars)
    assert order is None


def test_long_signal_on_strong_up_impulse_in_london_window() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1002),
        make_bar("2024-01-02 07:00", mid_open=1.1002, mid_high=1.1030, mid_low=1.1001, mid_close=1.1028),
    ]
    order = run_until_signal(strategy, bars)
    assert order is not None
    assert order.side == "long"


def test_short_signal_on_strong_down_impulse_in_new_york_window() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 12:30", mid_open=1.1050, mid_high=1.1052, mid_low=1.1048, mid_close=1.1050),
        make_bar("2024-01-02 12:45", mid_open=1.1050, mid_high=1.1051, mid_low=1.1045, mid_close=1.1046),
        make_bar("2024-01-02 13:00", mid_open=1.1046, mid_high=1.1047, mid_low=1.1018, mid_close=1.1020),
    ]
    order = run_until_signal(strategy, bars)
    assert order is not None
    assert order.side == "short"


def test_stop_and_target_direction_for_long() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1002),
        make_bar("2024-01-02 07:00", mid_open=1.1002, mid_high=1.1030, mid_low=1.1001, mid_close=1.1028),
    ]
    order = run_until_signal(strategy, bars)
    assert order is not None
    assert order.side == "long"
    assert order.stop_loss < order.entry_reference < order.take_profit


def test_no_signal_outside_open_windows() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 09:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 09:15", mid_open=1.1000, mid_high=1.1004, mid_low=1.0999, mid_close=1.1003),
        make_bar("2024-01-02 09:30", mid_open=1.1003, mid_high=1.1032, mid_low=1.1002, mid_close=1.1030),
    ]
    order = run_until_signal(strategy, bars)
    assert order is None
