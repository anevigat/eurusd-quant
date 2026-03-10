from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.asian_range_compression_breakout import (
    AsianRangeCompressionBreakoutConfig,
    AsianRangeCompressionBreakoutStrategy,
)


def _config(
    *,
    compression_atr_ratio: float = 2.0,
) -> AsianRangeCompressionBreakoutConfig:
    return AsianRangeCompressionBreakoutConfig(
        timeframe="15m",
        asian_start_utc="00:00",
        asian_end_utc="06:00",
        entry_start_utc="07:00",
        entry_end_utc="10:00",
        atr_period=1,
        compression_atr_ratio=compression_atr_ratio,
        breakout_buffer_pips=0.5,
        stop_atr_multiple=1.0,
        exit_model="atr_target",
        atr_target_multiple=1.5,
        max_holding_bars=12,
        one_trade_per_day=True,
    )


def _bar(
    ts: str,
    bid_high: float,
    ask_low: float,
    bid_close: float,
    ask_close: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
) -> pd.Series:
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


def test_compression_condition_works_for_long_breakout() -> None:
    strategy = AsianRangeCompressionBreakoutStrategy(_config(compression_atr_ratio=2.0))
    strategy.generate_order(
        _bar(
            "2024-01-02 00:00:00",
            bid_high=1.1005,
            ask_low=1.1000,
            bid_close=1.1002,
            ask_close=1.1003,
            mid_high=1.1005,
            mid_low=1.1000,
            mid_close=1.10025,
        ),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 07:00:00",
            bid_high=1.1008,
            ask_low=1.1002,
            bid_close=1.1007,
            ask_close=1.1008,
            mid_high=1.1008,
            mid_low=1.1003,
            mid_close=1.10075,
        ),
        False,
        False,
    )
    assert order is not None
    assert order.side == "long"


def test_breakout_signal_generation_for_short() -> None:
    strategy = AsianRangeCompressionBreakoutStrategy(_config(compression_atr_ratio=2.0))
    strategy.generate_order(
        _bar(
            "2024-01-02 00:00:00",
            bid_high=1.1005,
            ask_low=1.1000,
            bid_close=1.1002,
            ask_close=1.1003,
            mid_high=1.1005,
            mid_low=1.1000,
            mid_close=1.10025,
        ),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 07:15:00",
            bid_high=1.1002,
            ask_low=1.0995,
            bid_close=1.0994,
            ask_close=1.0995,
            mid_high=1.1002,
            mid_low=1.0995,
            mid_close=1.09945,
        ),
        False,
        False,
    )
    assert order is not None
    assert order.side == "short"


def test_no_signal_when_compression_condition_fails() -> None:
    strategy = AsianRangeCompressionBreakoutStrategy(_config(compression_atr_ratio=0.6))
    strategy.generate_order(
        _bar(
            "2024-01-02 00:00:00",
            bid_high=1.1005,
            ask_low=1.1000,
            bid_close=1.1002,
            ask_close=1.1003,
            mid_high=1.1005,
            mid_low=1.1000,
            mid_close=1.10025,
        ),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 07:00:00",
            bid_high=1.1008,
            ask_low=1.1002,
            bid_close=1.1007,
            ask_close=1.1008,
            mid_high=1.1008,
            mid_low=1.1003,
            mid_close=1.10075,
        ),
        False,
        False,
    )
    assert order is None


def test_one_trade_per_day() -> None:
    strategy = AsianRangeCompressionBreakoutStrategy(_config(compression_atr_ratio=2.0))
    strategy.generate_order(
        _bar(
            "2024-01-02 00:00:00",
            bid_high=1.1005,
            ask_low=1.1000,
            bid_close=1.1002,
            ask_close=1.1003,
            mid_high=1.1005,
            mid_low=1.1000,
            mid_close=1.10025,
        ),
        False,
        False,
    )
    first_order = strategy.generate_order(
        _bar(
            "2024-01-02 07:00:00",
            bid_high=1.1008,
            ask_low=1.1002,
            bid_close=1.1007,
            ask_close=1.1008,
            mid_high=1.1008,
            mid_low=1.1003,
            mid_close=1.10075,
        ),
        False,
        False,
    )
    second_order = strategy.generate_order(
        _bar(
            "2024-01-02 07:15:00",
            bid_high=1.1010,
            ask_low=1.1004,
            bid_close=1.1009,
            ask_close=1.1010,
            mid_high=1.1010,
            mid_low=1.1004,
            mid_close=1.10095,
        ),
        False,
        False,
    )
    assert first_order is not None
    assert second_order is None
