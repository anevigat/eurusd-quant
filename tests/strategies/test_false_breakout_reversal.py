from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)


def _config(
    *,
    allowed_side: str = "both",
    entry_start_utc: str = "07:00",
    entry_end_utc: str = "10:00",
) -> FalseBreakoutReversalConfig:
    return FalseBreakoutReversalConfig(
        timeframe="15m",
        asian_range_start_utc="00:00",
        asian_range_end_utc="06:00",
        entry_start_utc=entry_start_utc,
        entry_end_utc=entry_end_utc,
        break_buffer_pips=0.5,
        reentry_buffer_pips=0.0,
        atr_period=1,
        atr_min_threshold=0.0,
        stop_mode="outside_break_extreme",
        stop_atr_buffer_multiple=0.0,
        take_profit_mode="range_midpoint",
        take_profit_r=1.5,
        max_holding_bars=12,
        allowed_side=allowed_side,
        one_trade_per_day=True,
    )


def _bar(
    ts: str,
    bid_high: float,
    bid_low: float,
    bid_close: float,
    ask_high: float,
    ask_low: float,
    ask_close: float,
    mid_close: float,
    mid_high: float | None = None,
    mid_low: float | None = None,
) -> pd.Series:
    if mid_high is None:
        mid_high = max(bid_high, ask_high)
    if mid_low is None:
        mid_low = min(bid_low, ask_low)
    return pd.Series(
        {
            "timestamp": pd.Timestamp(ts, tz="UTC"),
            "bid_high": bid_high,
            "bid_low": bid_low,
            "bid_close": bid_close,
            "ask_high": ask_high,
            "ask_low": ask_low,
            "ask_close": ask_close,
            "mid_high": mid_high,
            "mid_low": mid_low,
            "mid_close": mid_close,
        }
    )


def test_asian_range_built_correctly() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    bars = [
        _bar("2024-01-02 00:00:00", 1.1008, 1.1000, 1.1004, 1.1009, 1.1001, 1.1005, 1.10045),
        _bar("2024-01-02 05:45:00", 1.1006, 1.0999, 1.1002, 1.1007, 1.1000, 1.1003, 1.10025),
    ]
    for bar in bars:
        strategy.generate_order(bar, has_open_position=False, has_pending_order=False)

    assert strategy.current_asian_high == 1.1008
    assert strategy.current_asian_low == 1.1


def test_no_signal_before_false_breakout_occurs() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1009, 1.1001, 1.1005, 1.1010, 1.1002, 1.1006, 1.10055),
        False,
        False,
    )
    assert order is None


def test_long_signal_after_break_below_then_close_back_inside() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    no_order = strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1005, 1.0994, 1.0997, 1.1006, 1.0995, 1.0998, 1.09975),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", 1.1006, 1.0999, 1.1002, 1.1007, 1.1000, 1.1003, 1.10025),
        False,
        False,
    )
    assert no_order is None
    assert order is not None
    assert order.side == "long"


def test_short_signal_after_break_above_then_close_back_inside() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    no_order = strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1016, 1.1008, 1.1014, 1.1017, 1.1009, 1.1015, 1.10145),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", 1.1011, 1.1002, 1.1007, 1.1012, 1.1003, 1.1008, 1.10075),
        False,
        False,
    )
    assert no_order is None
    assert order is not None
    assert order.side == "short"


def test_no_signal_outside_entry_window() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1005, 1.0994, 1.0997, 1.1006, 1.0995, 1.0998, 1.09975),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 10:00:00", 1.1006, 1.0999, 1.1002, 1.1007, 1.1000, 1.1003, 1.10025),
        False,
        False,
    )
    assert order is None


def test_one_trade_per_day_enforced() -> None:
    strategy = FalseBreakoutReversalStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1005, 1.0994, 1.0997, 1.1006, 1.0995, 1.0998, 1.09975),
        False,
        False,
    )
    first_order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", 1.1006, 1.0999, 1.1002, 1.1007, 1.1000, 1.1003, 1.10025),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 07:30:00", 1.1016, 1.1008, 1.1014, 1.1017, 1.1009, 1.1015, 1.10145),
        False,
        False,
    )
    second_order = strategy.generate_order(
        _bar("2024-01-02 07:45:00", 1.1011, 1.1002, 1.1007, 1.1012, 1.1003, 1.1008, 1.10075),
        False,
        False,
    )
    assert first_order is not None
    assert second_order is None


def test_long_only_blocks_short_signals() -> None:
    strategy = FalseBreakoutReversalStrategy(_config(allowed_side="long_only"))
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1016, 1.1008, 1.1014, 1.1017, 1.1009, 1.1015, 1.10145),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", 1.1011, 1.1002, 1.1007, 1.1012, 1.1003, 1.1008, 1.10075),
        False,
        False,
    )
    assert order is None


def test_short_only_blocks_long_signals() -> None:
    strategy = FalseBreakoutReversalStrategy(_config(allowed_side="short_only"))
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", 1.1010, 1.1000, 1.1006, 1.1011, 1.1001, 1.1007, 1.10065),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 07:00:00", 1.1005, 1.0994, 1.0997, 1.1006, 1.0995, 1.0998, 1.09975),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 07:15:00", 1.1006, 1.0999, 1.1002, 1.1007, 1.1000, 1.1003, 1.10025),
        False,
        False,
    )
    assert order is None
