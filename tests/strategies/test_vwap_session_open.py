from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.vwap_session_open import (
    VWAPSessionOpenConfig,
    VWAPSessionOpenStrategy,
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


def build_strategy() -> VWAPSessionOpenStrategy:
    cfg = VWAPSessionOpenConfig(
        timeframe="15m",
        atr_period=2,
        deviation_threshold_atr=1.0,
        london_window_start_utc="06:45",
        london_window_end_utc="07:15",
        new_york_window_start_utc="12:45",
        new_york_window_end_utc="13:15",
        stop_atr_multiple=1.2,
        max_holding_bars=8,
        one_trade_per_day=True,
    )
    return VWAPSessionOpenStrategy(cfg)


def run_bars(strategy: VWAPSessionOpenStrategy, bars: list[pd.Series]):
    order = None
    for bar in bars:
        order = strategy.generate_order(
            bar,
            has_open_position=False,
            has_pending_order=False,
        )
    return order


def test_no_signal_if_deviation_below_threshold() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1001),
        make_bar("2024-01-02 07:00", mid_open=1.1001, mid_high=1.1003, mid_low=1.1000, mid_close=1.1002),
    ]
    assert run_bars(strategy, bars) is None


def test_short_signal_on_positive_vwap_deviation_in_window() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 07:00", mid_open=1.1000, mid_high=1.1035, mid_low=1.0999, mid_close=1.1032),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "short"


def test_long_signal_on_negative_vwap_deviation_in_window() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 12:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 12:45", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 13:00", mid_open=1.1000, mid_high=1.1001, mid_low=1.0964, mid_close=1.0967),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "long"


def test_target_and_stop_sanity() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 06:30", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 06:45", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 07:00", mid_open=1.1000, mid_high=1.1035, mid_low=1.0999, mid_close=1.1032),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "short"
    assert order.take_profit < order.entry_reference < order.stop_loss


def test_no_signal_outside_windows() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 09:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 09:15", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 09:30", mid_open=1.1000, mid_high=1.1035, mid_low=1.0999, mid_close=1.1032),
    ]
    assert run_bars(strategy, bars) is None
