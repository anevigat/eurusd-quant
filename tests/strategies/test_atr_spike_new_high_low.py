from __future__ import annotations

import pandas as pd

from eurusd_quant.strategies.atr_spike_new_high_low import (
    ATRSpikeNewHighLowConfig,
    ATRSpikeNewHighLowStrategy,
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


def build_strategy() -> ATRSpikeNewHighLowStrategy:
    cfg = ATRSpikeNewHighLowConfig(
        timeframe="15m",
        atr_period=2,
        atr_median_lookback_bars=4,
        atr_spike_threshold=1.5,
        breakout_lookback_bars=3,
        stop_atr_multiple=1.0,
        target_atr_multiple=1.5,
        max_holding_bars=8,
        one_trade_per_day=False,
    )
    return ATRSpikeNewHighLowStrategy(cfg)


def run_bars(strategy: ATRSpikeNewHighLowStrategy, bars: list[pd.Series]):
    order = None
    for bar in bars:
        order = strategy.generate_order(
            bar,
            has_open_position=False,
            has_pending_order=False,
        )
    return order


def test_no_signal_when_atr_spike_below_threshold() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 00:15", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 00:30", mid_open=1.1001, mid_high=1.1004, mid_low=1.1000, mid_close=1.1002),
        make_bar("2024-01-02 00:45", mid_open=1.1002, mid_high=1.1005, mid_low=1.1001, mid_close=1.1003),
        make_bar("2024-01-02 01:00", mid_open=1.1003, mid_high=1.1006, mid_low=1.1002, mid_close=1.1004),
    ]
    order = run_bars(strategy, bars)
    assert order is None


def test_long_signal_when_spike_and_new_high() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 00:15", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 00:30", mid_open=1.1001, mid_high=1.1004, mid_low=1.1000, mid_close=1.1002),
        make_bar("2024-01-02 00:45", mid_open=1.1002, mid_high=1.1005, mid_low=1.1001, mid_close=1.1003),
        make_bar("2024-01-02 01:00", mid_open=1.1003, mid_high=1.1030, mid_low=1.1000, mid_close=1.1028),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "long"


def test_short_signal_when_spike_and_new_low() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 00:15", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 00:30", mid_open=1.1001, mid_high=1.1004, mid_low=1.1000, mid_close=1.1002),
        make_bar("2024-01-02 00:45", mid_open=1.1002, mid_high=1.1005, mid_low=1.1001, mid_close=1.1003),
        make_bar("2024-01-02 01:00", mid_open=1.1003, mid_high=1.1004, mid_low=1.0974, mid_close=1.0978),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "short"


def test_stop_and_target_direction_for_long() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 00:15", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 00:30", mid_open=1.1001, mid_high=1.1004, mid_low=1.1000, mid_close=1.1002),
        make_bar("2024-01-02 00:45", mid_open=1.1002, mid_high=1.1005, mid_low=1.1001, mid_close=1.1003),
        make_bar("2024-01-02 01:00", mid_open=1.1003, mid_high=1.1030, mid_low=1.1000, mid_close=1.1028),
    ]
    order = run_bars(strategy, bars)
    assert order is not None
    assert order.side == "long"
    assert order.stop_loss < order.entry_reference < order.take_profit


def test_no_signal_without_breakout() -> None:
    strategy = build_strategy()
    bars = [
        make_bar("2024-01-02 00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0998, mid_close=1.1000),
        make_bar("2024-01-02 00:15", mid_open=1.1000, mid_high=1.1003, mid_low=1.0999, mid_close=1.1001),
        make_bar("2024-01-02 00:30", mid_open=1.1001, mid_high=1.1004, mid_low=1.1000, mid_close=1.1002),
        make_bar("2024-01-02 00:45", mid_open=1.1002, mid_high=1.1005, mid_low=1.1001, mid_close=1.1003),
        make_bar("2024-01-02 01:00", mid_open=1.1003, mid_high=1.1005, mid_low=1.0999, mid_close=1.1003),
    ]
    order = run_bars(strategy, bars)
    assert order is None
