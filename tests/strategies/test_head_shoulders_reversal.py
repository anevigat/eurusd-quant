from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.head_shoulders_reversal import (
    HeadShouldersReversalConfig,
    HeadShouldersReversalStrategy,
)


def _config(
    *,
    atr_period: int = 1,
    shoulder_tolerance_atr: float = 0.5,
    head_min_excess_atr: float = 0.3,
    stop_atr_multiple: float = 1.0,
    target_atr_multiple: float = 1.5,
    max_holding_bars: int = 8,
    pattern_lookback_bars: int = 40,
    one_trade_per_day: bool = False,
) -> HeadShouldersReversalConfig:
    return HeadShouldersReversalConfig(
        timeframe="15m",
        atr_period=atr_period,
        shoulder_tolerance_atr=shoulder_tolerance_atr,
        head_min_excess_atr=head_min_excess_atr,
        stop_atr_multiple=stop_atr_multiple,
        target_atr_multiple=target_atr_multiple,
        max_holding_bars=max_holding_bars,
        pattern_lookback_bars=pattern_lookback_bars,
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


def _run_sequence(strategy: HeadShouldersReversalStrategy, bars: list[pd.Series]) -> object:
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    return order


def _bearish_pattern_bars(*, right_shoulder_high: float, head_high: float, break_close: float) -> list[pd.Series]:
    return [
        _bar("2024-01-02 06:30:00", mid_open=1.0995, mid_high=1.1002, mid_low=1.0990, mid_close=1.0998),
        _bar("2024-01-02 06:45:00", mid_open=1.0998, mid_high=1.1005, mid_low=1.0993, mid_close=1.1000),
        _bar("2024-01-02 07:00:00", mid_open=1.1000, mid_high=1.1020, mid_low=1.0995, mid_close=1.1015),
        _bar("2024-01-02 07:15:00", mid_open=1.1015, mid_high=1.1080, mid_low=1.1010, mid_close=1.1070),
        _bar("2024-01-02 07:30:00", mid_open=1.1070, mid_high=1.1040, mid_low=1.1000, mid_close=1.1020),
        _bar("2024-01-02 07:45:00", mid_open=1.1020, mid_high=1.1060, mid_low=1.1010, mid_close=1.1050),
        _bar("2024-01-02 08:00:00", mid_open=1.1050, mid_high=head_high, mid_low=1.1040, mid_close=1.1110),
        _bar("2024-01-02 08:15:00", mid_open=1.1110, mid_high=1.1060, mid_low=1.1000, mid_close=1.1010),
        _bar("2024-01-02 08:30:00", mid_open=1.1010, mid_high=right_shoulder_high, mid_low=1.1030, mid_close=1.1080),
        _bar("2024-01-02 08:45:00", mid_open=1.1080, mid_high=1.1030, mid_low=1.0970, mid_close=break_close),
    ]


def test_no_signal_when_shoulders_not_similar_enough() -> None:
    strategy = HeadShouldersReversalStrategy(_config())
    order = _run_sequence(
        strategy,
        _bearish_pattern_bars(right_shoulder_high=1.1030, head_high=1.1120, break_close=1.0980),
    )
    assert order is None


def test_no_signal_when_head_not_clearly_above_shoulders() -> None:
    strategy = HeadShouldersReversalStrategy(_config(head_min_excess_atr=0.3))
    order = _run_sequence(
        strategy,
        _bearish_pattern_bars(right_shoulder_high=1.1085, head_high=1.1090, break_close=1.0980),
    )
    assert order is None


def test_short_signal_on_bearish_neckline_break() -> None:
    strategy = HeadShouldersReversalStrategy(_config(head_min_excess_atr=0.2))
    order = _run_sequence(
        strategy,
        _bearish_pattern_bars(right_shoulder_high=1.1090, head_high=1.1120, break_close=1.0980),
    )
    assert order is not None
    assert order.side == "short"


def test_long_signal_on_inverse_neckline_break() -> None:
    strategy = HeadShouldersReversalStrategy(_config(head_min_excess_atr=0.2))
    bars = [
        _bar("2024-01-03 06:30:00", mid_open=1.0950, mid_high=1.0958, mid_low=1.0945, mid_close=1.0952),
        _bar("2024-01-03 06:45:00", mid_open=1.0952, mid_high=1.0960, mid_low=1.0948, mid_close=1.0950),
        _bar("2024-01-03 07:00:00", mid_open=1.0950, mid_high=1.0960, mid_low=1.0940, mid_close=1.0950),
        _bar("2024-01-03 07:15:00", mid_open=1.0950, mid_high=1.0970, mid_low=1.0920, mid_close=1.0930),
        _bar("2024-01-03 07:30:00", mid_open=1.0930, mid_high=1.0990, mid_low=1.0940, mid_close=1.0980),
        _bar("2024-01-03 07:45:00", mid_open=1.0980, mid_high=1.0980, mid_low=1.0930, mid_close=1.0940),
        _bar("2024-01-03 08:00:00", mid_open=1.0940, mid_high=1.0950, mid_low=1.0880, mid_close=1.0890),
        _bar("2024-01-03 08:15:00", mid_open=1.0890, mid_high=1.0990, mid_low=1.0920, mid_close=1.0980),
        _bar("2024-01-03 08:30:00", mid_open=1.0980, mid_high=1.0970, mid_low=1.0910, mid_close=1.0920),
        _bar("2024-01-03 08:45:00", mid_open=1.0920, mid_high=1.1010, mid_low=1.0930, mid_close=1.1000),
    ]
    order = _run_sequence(strategy, bars)
    assert order is not None
    assert order.side == "long"


def test_stop_and_target_initialized_correctly() -> None:
    strategy = HeadShouldersReversalStrategy(_config(head_min_excess_atr=0.2))
    order = _run_sequence(
        strategy,
        _bearish_pattern_bars(right_shoulder_high=1.1090, head_high=1.1120, break_close=1.0980),
    )
    assert order is not None
    assert order.stop_loss > order.entry_reference
    assert order.take_profit < order.entry_reference
    assert order.max_holding_bars == 8
    assert order.take_profit == pytest.approx(
        order.entry_reference - 1.5 * (order.stop_loss - order.entry_reference)
    )


def test_no_signal_without_neckline_break() -> None:
    strategy = HeadShouldersReversalStrategy(_config())
    order = _run_sequence(
        strategy,
        _bearish_pattern_bars(right_shoulder_high=1.1090, head_high=1.1120, break_close=1.1005),
    )
    assert order is None
