from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)
from eurusd_quant.utils import infer_pip_size


def _config(
    *,
    impulse_threshold_pips: float = 10.0,
    entry_start_utc: str = "13:30",
    entry_end_utc: str = "15:00",
    allowed_side: str = "both",
    retracement_entry_ratio: float = 0.5,
    exit_model: str = "retracement",
    atr_period: int = 14,
    atr_target_multiple: float = 1.0,
) -> NYImpulseMeanReversionConfig:
    return NYImpulseMeanReversionConfig(
        timeframe="15m",
        impulse_start_utc="13:00",
        impulse_end_utc="13:30",
        entry_start_utc=entry_start_utc,
        entry_end_utc=entry_end_utc,
        impulse_threshold_pips=impulse_threshold_pips,
        entry_mode="impulse_midpoint_cross",
        retracement_entry_ratio=retracement_entry_ratio,
        exit_model=exit_model,
        retracement_target_ratio=0.5,
        atr_period=atr_period,
        atr_target_multiple=atr_target_multiple,
        stop_buffer_pips=2.0,
        max_holding_bars=6,
        one_trade_per_day=True,
        allowed_side=allowed_side,
    )


def _bar(
    ts: str,
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


def _bullish_impulse_setup(strategy: NYImpulseMeanReversionStrategy, *, symbol: str = "EURUSD") -> None:
    strategy.generate_order(
        _bar("2024-01-02 13:00:00", 1.1000, 1.1010, 1.0998, 1.1008, symbol=symbol),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 13:15:00", 1.1008, 1.1014, 1.1006, 1.1012, symbol=symbol),
        False,
        False,
    )


def _bearish_impulse_setup(strategy: NYImpulseMeanReversionStrategy) -> None:
    strategy.generate_order(
        _bar("2024-01-02 13:00:00", 1.1010, 1.1012, 1.1002, 1.1004),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 13:15:00", 1.1004, 1.1005, 1.0994, 1.0998),
        False,
        False,
    )


def test_no_signal_if_impulse_below_threshold() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config(impulse_threshold_pips=20.0))
    strategy.generate_order(
        _bar("2024-01-02 13:00:00", 1.1000, 1.1003, 1.0999, 1.1002),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 13:15:00", 1.1002, 1.1004, 1.1001, 1.1003),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1003, 1.1004, 1.1000, 1.1001),
        False,
        False,
    )
    assert order is None


def test_bullish_impulse_close_back_below_midpoint_generates_short() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config())
    _bullish_impulse_setup(strategy)
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1002, 1.1004),
        False,
        False,
    )
    assert order is not None
    assert order.side == "short"


def test_bearish_impulse_close_back_above_midpoint_generates_long() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config())
    _bearish_impulse_setup(strategy)
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.0998, 1.1006, 1.0997, 1.1005),
        False,
        False,
    )
    assert order is not None
    assert order.side == "long"


def test_no_signal_outside_entry_window() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config(entry_start_utc="13:30", entry_end_utc="15:00"))
    _bullish_impulse_setup(strategy)
    order = strategy.generate_order(
        _bar("2024-01-02 15:00:00", 1.1012, 1.1013, 1.1002, 1.1004),
        False,
        False,
    )
    assert order is None


def test_one_trade_per_day_enforced() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config())
    _bullish_impulse_setup(strategy)
    first_order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1002, 1.1004),
        False,
        False,
    )
    second_order = strategy.generate_order(
        _bar("2024-01-02 13:45:00", 1.1004, 1.1006, 1.1001, 1.1002),
        False,
        False,
    )
    assert first_order is not None
    assert second_order is None


def test_stop_and_target_computed_from_impulse_range() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config())
    _bullish_impulse_setup(strategy)
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1002, 1.1004),
        False,
        False,
    )
    assert order is not None

    # Impulse high/low from setup: 1.1014 / 1.0998 (range 0.0016)
    # Stop buffer: 2 pips = 0.0002
    # Entry reference for short = bid_close of 13:30 bar = 1.10035
    # TP distance = 0.5 * 0.0016 = 0.0008 -> 1.09955
    assert order.stop_loss == pytest.approx(1.1016)
    assert order.take_profit == pytest.approx(1.09955)


def test_retracement_entry_ratio_changes_trigger_level() -> None:
    strategy_early = NYImpulseMeanReversionStrategy(_config(retracement_entry_ratio=0.3))
    _bullish_impulse_setup(strategy_early)
    early_order = strategy_early.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1007, 1.1008),
        False,
        False,
    )

    strategy_mid = NYImpulseMeanReversionStrategy(_config(retracement_entry_ratio=0.5))
    _bullish_impulse_setup(strategy_mid)
    mid_order = strategy_mid.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1007, 1.1008),
        False,
        False,
    )

    assert early_order is not None
    assert early_order.side == "short"
    assert mid_order is None


def test_atr_exit_target_uses_atr_multiple() -> None:
    strategy = NYImpulseMeanReversionStrategy(
        _config(exit_model="atr", atr_period=1, atr_target_multiple=1.0)
    )
    _bullish_impulse_setup(strategy)
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1002, 1.1004),
        False,
        False,
    )
    assert order is not None

    # With atr_period=1, ATR at signal bar equals TR of 13:30 bar.
    # TR = max(1.1013-1.1002, |1.1013-1.1012|, |1.1002-1.1012|) = 0.0011.
    # Entry reference short = bid_close = 1.10035 -> TP = 1.09925.
    assert order.stop_loss == pytest.approx(1.1016)
    assert order.take_profit == pytest.approx(1.09925)


def test_infer_pip_size_for_common_pairs() -> None:
    assert infer_pip_size("EURUSD") == pytest.approx(0.0001)
    assert infer_pip_size("GBPUSD") == pytest.approx(0.0001)
    assert infer_pip_size("USDJPY") == pytest.approx(0.01)


def test_generated_order_uses_symbol_from_input_bars() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config())
    _bullish_impulse_setup(strategy, symbol="GBPUSD")
    order = strategy.generate_order(
        _bar("2024-01-02 13:30:00", 1.1012, 1.1013, 1.1002, 1.1004, symbol="GBPUSD"),
        False,
        False,
    )
    assert order is not None
    assert order.symbol == "GBPUSD"


def test_usdjpy_uses_jpy_pip_size_for_threshold_and_stop_buffer() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config(impulse_threshold_pips=30.0))
    strategy.generate_order(
        _bar(
            "2024-01-02 13:00:00",
            150.00,
            150.20,
            149.90,
            150.15,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    strategy.generate_order(
        _bar(
            "2024-01-02 13:15:00",
            150.15,
            150.25,
            150.10,
            150.22,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 13:30:00",
            150.22,
            150.23,
            150.00,
            150.05,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    assert order is not None
    assert order.symbol == "USDJPY"
    assert order.stop_loss == pytest.approx(150.27)
    assert order.take_profit == pytest.approx(149.87)


def test_usdjpy_threshold_blocks_signal_when_impulse_too_small() -> None:
    strategy = NYImpulseMeanReversionStrategy(_config(impulse_threshold_pips=40.0))
    strategy.generate_order(
        _bar(
            "2024-01-02 13:00:00",
            150.00,
            150.20,
            149.90,
            150.15,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    strategy.generate_order(
        _bar(
            "2024-01-02 13:15:00",
            150.15,
            150.25,
            150.10,
            150.22,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 13:30:00",
            150.22,
            150.23,
            150.00,
            150.05,
            spread=0.01,
            symbol="USDJPY",
        ),
        False,
        False,
    )
    assert order is None
