from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy


def _config() -> SessionBreakoutConfig:
    return SessionBreakoutConfig(
        timeframe="15m",
        asian_range_start_utc="00:00",
        asian_range_end_utc="06:00",
        entry_start_utc="07:00",
        entry_end_utc="10:00",
        atr_period=1,
        atr_min_threshold=0.0,
        stop_atr_multiple=1.0,
        take_profit_r=1.5,
        max_holding_bars=12,
    )


def _bar(
    ts: str,
    bid_high: float,
    ask_low: float,
    bid_close: float,
    ask_close: float,
    mid_close: float,
    mid_high: float | None = None,
    mid_low: float | None = None,
) -> pd.Series:
    if mid_high is None:
        mid_high = max(mid_close, bid_high)
    if mid_low is None:
        mid_low = min(mid_close, ask_low)
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "bid_high": bid_high,
            "ask_low": ask_low,
            "bid_close": bid_close,
            "ask_close": ask_close,
            "mid_high": mid_high,
            "mid_low": mid_low,
            "mid_close": mid_close,
        }
    )


def test_asian_range_calculated_correctly() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    asian_bars = [
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        _bar("2024-01-02 00:15:00", bid_high=1.1008, ask_low=1.0996, bid_close=1.1000, ask_close=1.1001, mid_close=1.10005),
        _bar("2024-01-02 05:45:00", bid_high=1.1006, ask_low=1.0997, bid_close=1.1002, ask_close=1.1003, mid_close=1.10025),
    ]
    for bar in asian_bars:
        strategy.generate_order(bar, has_open_position=False, has_pending_order=False)

    assert strategy.current_asian_high == 1.1008
    assert strategy.current_asian_low == 1.0996


def test_long_signal_when_bid_close_breaks_asian_high() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:00:00", bid_high=1.1006, ask_low=1.0999, bid_close=1.1007, ask_close=1.1008, mid_close=1.10075),
        False,
        False,
    )
    assert order is not None
    assert order.side == "long"


def test_short_signal_when_ask_close_breaks_asian_low() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", bid_high=1.1000, ask_low=1.0997, bid_close=1.0995, ask_close=1.0996, mid_close=1.09955),
        False,
        False,
    )
    assert order is not None
    assert order.side == "short"


def test_no_signal_outside_entry_window() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 10:15:00", bid_high=1.1010, ask_low=1.0999, bid_close=1.1011, ask_close=1.1012, mid_close=1.10115),
        False,
        False,
    )
    assert order is None


def test_one_trade_per_day() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        False,
        False,
    )
    first_order = strategy.generate_order(
        _bar("2024-01-02 07:00:00", bid_high=1.1006, ask_low=1.0999, bid_close=1.1007, ask_close=1.1008, mid_close=1.10075),
        False,
        False,
    )
    second_order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", bid_high=1.1007, ask_low=1.1000, bid_close=1.1009, ask_close=1.1010, mid_close=1.10095),
        False,
        False,
    )
    assert first_order is not None
    assert second_order is None


def test_entry_window_end_is_exclusive() -> None:
    strategy = SessionRangeBreakoutStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", bid_high=1.1005, ask_low=1.0998, bid_close=1.1001, ask_close=1.1002, mid_close=1.10015),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 10:00:00", bid_high=1.1010, ask_low=1.1000, bid_close=1.1011, ask_close=1.1012, mid_close=1.10115),
        False,
        False,
    )
    assert order is None


def test_atr_uses_true_range_not_close_to_close() -> None:
    cfg = SessionBreakoutConfig(
        timeframe="15m",
        asian_range_start_utc="00:00",
        asian_range_end_utc="06:00",
        entry_start_utc="07:00",
        entry_end_utc="10:00",
        atr_period=1,
        atr_min_threshold=0.0006,
        stop_atr_multiple=1.0,
        take_profit_r=1.5,
        max_holding_bars=12,
    )
    strategy = SessionRangeBreakoutStrategy(cfg)

    strategy.generate_order(
        _bar(
            "2024-01-02 00:00:00",
            bid_high=1.1005,
            ask_low=1.0998,
            bid_close=1.1001,
            ask_close=1.1002,
            mid_close=1.10015,
            mid_high=1.10080,
            mid_low=1.09990,
        ),
        False,
        False,
    )

    order = strategy.generate_order(
        _bar(
            "2024-01-02 07:00:00",
            bid_high=1.1006,
            ask_low=1.0999,
            bid_close=1.1007,
            ask_close=1.1008,
            mid_close=1.10015,
            mid_high=1.10085,
            mid_low=1.10010,
        ),
        False,
        False,
    )
    assert order is not None
