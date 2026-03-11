from __future__ import annotations

import pandas as pd

from eurusd_quant.live.strategy_registry import get_strategy, list_strategies


REQUIRED_SIGNAL_KEYS = {
    "timestamp",
    "strategy",
    "symbol",
    "side",
    "entry_price",
    "stop_price",
    "target_price",
}


def _bar(
    ts: str,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
    spread: float = 0.0001,
) -> dict:
    half = spread / 2.0
    return {
        "timestamp": pd.Timestamp(ts, tz="UTC"),
        "mid_open": mid_open,
        "mid_high": mid_high,
        "mid_low": mid_low,
        "mid_close": mid_close,
        "bid_close": mid_close - half,
        "ask_close": mid_close + half,
    }


def test_registry_contains_ny_impulse_strategy() -> None:
    names = list_strategies()
    assert "ny_impulse_mean_reversion" in names


def test_ny_live_strategy_returns_signal_schema() -> None:
    strategy_cls = get_strategy("ny_impulse_mean_reversion")
    strategy = strategy_cls()

    # Construct bars to trigger bullish-impulse then cross-down short signal at latest bar.
    bars = pd.DataFrame(
        [
            _bar("2024-01-02 13:00:00", 1.1000, 1.1015, 1.0998, 1.1012),
            _bar("2024-01-02 13:15:00", 1.1012, 1.1030, 1.1004, 1.1025),
            _bar("2024-01-02 13:30:00", 1.1025, 1.1026, 1.1008, 1.1010),
        ]
    )

    signal = strategy.evaluate_latest(bars)

    assert signal is not None
    assert REQUIRED_SIGNAL_KEYS.issubset(signal.keys())
    assert signal["strategy"] == "ny_impulse_mean_reversion"
    assert signal["symbol"] == "EURUSD"
    assert signal["side"] in {"long", "short"}
