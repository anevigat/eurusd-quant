from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.vwap_intraday_reversion import (
    VWAPIntradayReversionConfig,
    VWAPIntradayReversionStrategy,
)


def _config(
    *,
    session_start_utc: str = "07:00",
    session_end_utc: str = "17:00",
    atr_period: int = 1,
    deviation_threshold_atr: float = 0.25,
    stop_atr_multiple: float = 1.0,
    target_reversion_ratio: float = 0.5,
) -> VWAPIntradayReversionConfig:
    return VWAPIntradayReversionConfig(
        timeframe="15m",
        session_start_utc=session_start_utc,
        session_end_utc=session_end_utc,
        atr_period=atr_period,
        deviation_threshold_atr=deviation_threshold_atr,
        stop_atr_multiple=stop_atr_multiple,
        target_reversion_ratio=target_reversion_ratio,
        max_holding_bars=4,
        one_trade_per_day=True,
    )


def _bar(
    ts: str,
    *,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
    spread: float = 0.0002,
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


def test_no_signal_when_deviation_below_threshold() -> None:
    strategy = VWAPIntradayReversionStrategy(_config(deviation_threshold_atr=0.5))
    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1010,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is None


def test_short_signal_when_price_is_sufficiently_above_vwap() -> None:
    strategy = VWAPIntradayReversionStrategy(_config(deviation_threshold_atr=0.25))
    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1019,
            symbol="GBPUSD",
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is not None
    assert order.side == "short"
    assert order.symbol == "GBPUSD"


def test_long_signal_when_price_is_sufficiently_below_vwap() -> None:
    strategy = VWAPIntradayReversionStrategy(_config(deviation_threshold_atr=0.25))
    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1001,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is not None
    assert order.side == "long"


def test_target_price_is_partial_reversion_toward_vwap() -> None:
    strategy = VWAPIntradayReversionStrategy(_config(deviation_threshold_atr=0.25))
    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1019,
            spread=0.0002,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is not None

    # Typical/vwap proxy on first bar: (1.1020 + 1.1000 + 1.1019) / 3 = 1.1013
    # Short entry reference = bid_close = 1.1018
    # Target distance = 0.5 * |1.1018 - 1.1013| = 0.00025
    assert order.take_profit == pytest.approx(1.10155)


def test_stop_loss_is_atr_based() -> None:
    strategy = VWAPIntradayReversionStrategy(
        _config(deviation_threshold_atr=0.25, atr_period=1, stop_atr_multiple=1.0)
    )
    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1019,
            spread=0.0002,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is not None
    # ATR(period=1) = high-low = 0.0020, short stop = entry + ATR
    assert order.stop_loss == pytest.approx(1.1038)


def test_no_signal_outside_session_window() -> None:
    strategy = VWAPIntradayReversionStrategy(_config(session_start_utc="07:00", session_end_utc="17:00"))
    order = strategy.generate_order(
        _bar(
            "2024-01-02 17:00:00",
            mid_open=1.1010,
            mid_high=1.1020,
            mid_low=1.1000,
            mid_close=1.1019,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert order is None
