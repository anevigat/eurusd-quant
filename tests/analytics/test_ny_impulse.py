from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.analytics.ny_impulse import (
    assign_event_volatility_regimes,
    compute_impulse_events,
    summarize_trade_density,
)


def _bar(
    ts: str,
    *,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
) -> dict[str, object]:
    spread = 0.0001
    half = spread / 2.0
    return {
        "timestamp": pd.Timestamp(ts, tz="UTC"),
        "symbol": "EURUSD",
        "timeframe": "15m",
        "bid_open": mid_open - half,
        "bid_high": mid_high - half,
        "bid_low": mid_low - half,
        "bid_close": mid_close - half,
        "ask_open": mid_open + half,
        "ask_high": mid_high + half,
        "ask_low": mid_low + half,
        "ask_close": mid_close + half,
        "mid_open": mid_open,
        "mid_high": mid_high,
        "mid_low": mid_low,
        "mid_close": mid_close,
        "spread_open": spread,
        "spread_high": spread,
        "spread_low": spread,
        "spread_close": spread,
    }


def test_compute_impulse_events_builds_forward_returns() -> None:
    bars = pd.DataFrame(
        [
            _bar("2024-01-02 13:00:00", mid_open=1.1000, mid_high=1.1010, mid_low=1.0998, mid_close=1.1008),
            _bar("2024-01-02 13:15:00", mid_open=1.1008, mid_high=1.1015, mid_low=1.1007, mid_close=1.1012),
            _bar("2024-01-02 13:30:00", mid_open=1.1012, mid_high=1.1013, mid_low=1.1003, mid_close=1.1005),
            _bar("2024-01-02 13:45:00", mid_open=1.1005, mid_high=1.1006, mid_low=1.0998, mid_close=1.1000),
            _bar("2024-01-02 14:00:00", mid_open=1.1000, mid_high=1.1002, mid_low=1.0997, mid_close=1.0999),
        ]
    )

    events = compute_impulse_events(bars, forward_horizons=(1, 2))

    assert len(events) == 1
    row = events.iloc[0]
    assert row["impulse_direction"] == "up"
    assert row["impulse_size"] == pytest.approx(0.0017)
    assert row["forward_return_1"] == pytest.approx(-0.0007)
    assert row["signed_reversion_return_1"] == pytest.approx(0.0007)
    assert row["forward_return_2"] == pytest.approx(-0.0012)


def test_assign_event_volatility_regimes_labels_events() -> None:
    events = pd.DataFrame(
        {
            "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "atr": [0.0010, 0.0020, 0.0030],
        }
    )
    labeled, thresholds = assign_event_volatility_regimes(events)

    assert thresholds["low_quantile_threshold"] == pytest.approx(0.0016)
    assert thresholds["high_quantile_threshold"] == pytest.approx(0.0024)
    assert list(labeled["volatility_regime"]) == ["low_vol", "mid_vol", "high_vol"]


def test_summarize_trade_density_tracks_missing_months_and_windows() -> None:
    trades = pd.DataFrame(
        {
            "signal_time": [
                pd.Timestamp("2024-01-02 13:30:00", tz="UTC"),
                pd.Timestamp("2024-01-15 14:00:00", tz="UTC"),
                pd.Timestamp("2024-03-05 14:15:00", tz="UTC"),
            ],
            "entry_time": [
                pd.Timestamp("2024-01-02 13:45:00", tz="UTC"),
                pd.Timestamp("2024-01-15 14:15:00", tz="UTC"),
                pd.Timestamp("2024-03-05 14:30:00", tz="UTC"),
            ],
            "exit_time": [
                pd.Timestamp("2024-01-02 14:15:00", tz="UTC"),
                pd.Timestamp("2024-01-15 14:45:00", tz="UTC"),
                pd.Timestamp("2024-03-05 15:00:00", tz="UTC"),
            ],
            "net_pnl": [0.0010, -0.0005, 0.0007],
            "gross_pnl": [0.0010, -0.0005, 0.0007],
        }
    )

    summary, yearly, monthly, signal_windows, zero_trade_months = summarize_trade_density(trades)

    assert summary["total_trades"] == 3
    assert summary["zero_trade_month_count"] == 1
    assert summary["longest_zero_trade_gap_months"] == 1
    assert set(monthly["month"]) == {"2024-01", "2024-03"}
    assert set(signal_windows["signal_window_utc"]) == {"13:30", "14:00", "14:15"}
    assert yearly.iloc[0]["trade_count"] == 3
    assert zero_trade_months.iloc[0]["month"] == "2024-02"
