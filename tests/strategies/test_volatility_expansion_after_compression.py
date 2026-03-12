from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.strategies.volatility_expansion_after_compression import (
    VolatilityExpansionAfterCompressionConfig,
    VolatilityExpansionAfterCompressionStrategy,
)


def _config(
    *,
    atr_period: int = 1,
    compression_threshold: float = 0.8,
    compression_lookback_bars: int = 3,
    stop_atr_multiple: float = 1.0,
    target_atr_multiple: float = 1.5,
    max_holding_bars: int = 8,
    one_trade_per_day: bool = False,
) -> VolatilityExpansionAfterCompressionConfig:
    return VolatilityExpansionAfterCompressionConfig(
        timeframe="15m",
        atr_period=atr_period,
        compression_threshold=compression_threshold,
        compression_lookback_bars=compression_lookback_bars,
        stop_atr_multiple=stop_atr_multiple,
        target_atr_multiple=target_atr_multiple,
        max_holding_bars=max_holding_bars,
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


def test_no_signal_when_not_in_compressed_regime() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(_config(compression_threshold=0.5))
    bars = [
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.1000, mid_close=1.1005),
        _bar("2024-01-02 00:15:00", mid_open=1.1005, mid_high=1.1015, mid_low=1.1005, mid_close=1.1010),
        _bar("2024-01-02 00:30:00", mid_open=1.1010, mid_high=1.1020, mid_low=1.1010, mid_close=1.1016),
        _bar("2024-01-02 00:45:00", mid_open=1.1016, mid_high=1.1030, mid_low=1.1016, mid_close=1.1028),
    ]
    order = None
    for bar in bars:
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
    assert order is None


def test_long_signal_when_compression_breaks_upward() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.1000, mid_close=1.1005),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:15:00", mid_open=1.1005, mid_high=1.1012, mid_low=1.1002, mid_close=1.1006),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:30:00", mid_open=1.1006, mid_high=1.1011, mid_low=1.1009, mid_close=1.1010),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 00:45:00", mid_open=1.1010, mid_high=1.1017, mid_low=1.1012, mid_close=1.1016),
        False,
        False,
    )

    assert order is not None
    assert order.side == "long"


def test_short_signal_when_compression_breaks_downward() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", mid_open=1.2000, mid_high=1.2010, mid_low=1.2000, mid_close=1.2005),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:15:00", mid_open=1.2005, mid_high=1.2012, mid_low=1.2002, mid_close=1.2006),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:30:00", mid_open=1.2006, mid_high=1.2011, mid_low=1.2009, mid_close=1.2010),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 00:45:00", mid_open=1.2010, mid_high=1.2003, mid_low=1.1996, mid_close=1.1998),
        False,
        False,
    )

    assert order is not None
    assert order.side == "short"


def test_stop_and_target_are_atr_based() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(
        _config(stop_atr_multiple=1.0, target_atr_multiple=1.5)
    )
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.1000, mid_close=1.1005),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:15:00", mid_open=1.1005, mid_high=1.1012, mid_low=1.1002, mid_close=1.1006),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:30:00", mid_open=1.1006, mid_high=1.1011, mid_low=1.1009, mid_close=1.1010),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 00:45:00", mid_open=1.1010, mid_high=1.1017, mid_low=1.1012, mid_close=1.1016),
        False,
        False,
    )

    assert order is not None
    # ATR(period=1) on signal bar uses TR with previous close:
    # max(high-low, |high-prev_close|, |low-prev_close|) = 0.0007
    # long entry reference = ask_close = 1.10165
    assert order.stop_loss == pytest.approx(1.10095)
    assert order.take_profit == pytest.approx(1.10270)


def test_max_holding_bars_is_taken_from_config() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(_config(max_holding_bars=5))
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.1000, mid_close=1.1005),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:15:00", mid_open=1.1005, mid_high=1.1012, mid_low=1.1002, mid_close=1.1006),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:30:00", mid_open=1.1006, mid_high=1.1011, mid_low=1.1009, mid_close=1.1010),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 00:45:00", mid_open=1.1010, mid_high=1.1017, mid_low=1.1012, mid_close=1.1016),
        False,
        False,
    )
    assert order is not None
    assert order.max_holding_bars == 5


def test_no_signal_if_breakout_does_not_occur() -> None:
    strategy = VolatilityExpansionAfterCompressionStrategy(_config())
    strategy.generate_order(
        _bar("2024-01-02 00:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.1000, mid_close=1.1005),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:15:00", mid_open=1.1005, mid_high=1.1012, mid_low=1.1002, mid_close=1.1006),
        False,
        False,
    )
    strategy.generate_order(
        _bar("2024-01-02 00:30:00", mid_open=1.1006, mid_high=1.1011, mid_low=1.1009, mid_close=1.1010),
        False,
        False,
    )
    order = strategy.generate_order(
        _bar("2024-01-02 00:45:00", mid_open=1.1010, mid_high=1.1011, mid_low=1.1006, mid_close=1.1009),
        False,
        False,
    )
    assert order is None
