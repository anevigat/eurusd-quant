from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.london_pullback_continuation import (
    LondonPullbackContinuationConfig,
    LondonPullbackContinuationStrategy,
)


def _config(
    *,
    entry_start_utc: str = "08:00",
    entry_end_utc: str = "10:00",
    drift_threshold_pips: float = 8.0,
) -> LondonPullbackContinuationConfig:
    return LondonPullbackContinuationConfig(
        timeframe="15m",
        drift_start_utc="00:00",
        drift_end_utc="07:45",
        entry_start_utc=entry_start_utc,
        entry_end_utc=entry_end_utc,
        drift_threshold_pips=drift_threshold_pips,
        pullback_mode="ema20",
        atr_period=1,
        atr_min_threshold=0.0,
        stop_mode="atr",
        stop_atr_multiple=1.0,
        exit_model="atr_target",
        atr_target_multiple=1.2,
        max_holding_bars=12,
        one_trade_per_day=True,
        allowed_side="both",
    )


def _bar(
    ts: str,
    mid_close: float,
    mid_high: float,
    mid_low: float,
    spread: float = 0.0001,
) -> pd.Series:
    half_spread = spread / 2.0
    bid_close = mid_close - half_spread
    ask_close = mid_close + half_spread
    bid_high = mid_high - half_spread
    ask_high = mid_high + half_spread
    bid_low = mid_low - half_spread
    ask_low = mid_low + half_spread
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "mid_close": mid_close,
            "mid_high": mid_high,
            "mid_low": mid_low,
            "bid_close": bid_close,
            "ask_close": ask_close,
            "bid_high": bid_high,
            "ask_high": ask_high,
            "bid_low": bid_low,
            "ask_low": ask_low,
        }
    )


def test_no_signal_when_drift_magnitude_is_below_threshold() -> None:
    strategy = LondonPullbackContinuationStrategy(_config(drift_threshold_pips=8.0))
    bars = [
        _bar("2024-01-02 00:00:00", 1.1000, 1.1002, 1.0998),
        _bar("2024-01-02 07:45:00", 1.1004, 1.1006, 1.1002),  # +4 pips drift
        _bar("2024-01-02 08:00:00", 1.1000, 1.1002, 1.0998),
        _bar("2024-01-02 08:15:00", 1.1005, 1.1007, 1.1003),
    ]
    orders = [
        strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
        for bar in bars
    ]
    assert all(order is None for order in orders)


def test_long_signal_after_up_drift_pullback_and_close_back_above_ema() -> None:
    strategy = LondonPullbackContinuationStrategy(_config())
    strategy.generate_order(_bar("2024-01-02 00:00:00", 1.1000, 1.1002, 1.0998), False, False)
    strategy.generate_order(_bar("2024-01-02 07:45:00", 1.1010, 1.1012, 1.1008), False, False)
    no_order = strategy.generate_order(
        _bar("2024-01-02 08:00:00", 1.1000, 1.1002, 1.0998),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 08:15:00", 1.1005, 1.1007, 1.1003),
        False,
        False,
    )
    assert no_order is None
    assert order is not None
    assert order.side == "long"


def test_short_signal_after_down_drift_pullback_and_close_back_below_ema() -> None:
    strategy = LondonPullbackContinuationStrategy(_config())
    strategy.generate_order(_bar("2024-01-02 00:00:00", 1.1000, 1.1002, 1.0998), False, False)
    strategy.generate_order(_bar("2024-01-02 07:45:00", 1.0990, 1.0992, 1.0988), False, False)
    no_order = strategy.generate_order(
        _bar("2024-01-02 08:00:00", 1.1000, 1.1002, 1.0997),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 08:15:00", 1.0992, 1.0994, 1.0990),
        False,
        False,
    )
    assert no_order is None
    assert order is not None
    assert order.side == "short"


def test_no_signal_outside_entry_window() -> None:
    strategy = LondonPullbackContinuationStrategy(_config(entry_start_utc="08:00", entry_end_utc="10:00"))
    strategy.generate_order(_bar("2024-01-02 00:00:00", 1.1000, 1.1002, 1.0998), False, False)
    strategy.generate_order(_bar("2024-01-02 07:45:00", 1.1010, 1.1012, 1.1008), False, False)
    strategy.generate_order(_bar("2024-01-02 09:45:00", 1.1000, 1.1002, 1.0998), False, False)
    order = strategy.generate_order(
        _bar("2024-01-02 10:00:00", 1.1005, 1.1007, 1.1003),
        False,
        False,
    )
    assert order is None


def test_one_trade_per_day_enforced() -> None:
    strategy = LondonPullbackContinuationStrategy(_config())
    strategy.generate_order(_bar("2024-01-02 00:00:00", 1.1000, 1.1002, 1.0998), False, False)
    strategy.generate_order(_bar("2024-01-02 07:45:00", 1.1010, 1.1012, 1.1008), False, False)
    strategy.generate_order(_bar("2024-01-02 08:00:00", 1.1000, 1.1002, 1.0998), False, False)
    first_order = strategy.generate_order(
        _bar("2024-01-02 08:15:00", 1.1005, 1.1007, 1.1003),
        False,
        False,
    )
    strategy.generate_order(_bar("2024-01-02 08:30:00", 1.1001, 1.1003, 1.0999), False, False)
    second_order = strategy.generate_order(
        _bar("2024-01-02 08:45:00", 1.1006, 1.1008, 1.1004),
        False,
        False,
    )
    assert first_order is not None
    assert second_order is None
