from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.analytics.session_structure import (
    assign_regimes,
    build_session_records,
    build_transition_records,
    compute_fx_session_date,
    label_session,
)


def _bar(ts: str, *, mid_open: float, mid_high: float, mid_low: float, mid_close: float) -> dict[str, object]:
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


def test_label_session_uses_existing_repo_windows() -> None:
    assert label_session(pd.Timestamp("2024-01-02 00:15:00", tz="UTC")) == "asia"
    assert label_session(pd.Timestamp("2024-01-02 07:00:00", tz="UTC")) == "london"
    assert label_session(pd.Timestamp("2024-01-02 13:00:00", tz="UTC")) == "new_york"
    assert label_session(pd.Timestamp("2024-01-02 22:30:00", tz="UTC")) == "new_york"


def test_compute_fx_session_date_respects_22utc_rollover() -> None:
    timestamps = pd.Series(
        [
            pd.Timestamp("2024-01-01 21:45:00", tz="UTC"),
            pd.Timestamp("2024-01-01 22:00:00", tz="UTC"),
            pd.Timestamp("2024-01-02 00:15:00", tz="UTC"),
        ]
    )
    values = compute_fx_session_date(timestamps)

    assert str(values.iloc[0]) == "2024-01-01"
    assert str(values.iloc[1]) == "2024-01-02"
    assert str(values.iloc[2]) == "2024-01-02"


def test_build_session_records_computes_efficiency_and_clv() -> None:
    bars = pd.DataFrame(
        [
            _bar("2024-01-01 22:00:00", mid_open=1.1000, mid_high=1.1004, mid_low=1.0999, mid_close=1.1002),
            _bar("2024-01-01 22:15:00", mid_open=1.1002, mid_high=1.1006, mid_low=1.1001, mid_close=1.1004),
            _bar("2024-01-02 00:00:00", mid_open=1.1004, mid_high=1.1009, mid_low=1.1003, mid_close=1.1008),
            _bar("2024-01-02 00:15:00", mid_open=1.1008, mid_high=1.1011, mid_low=1.1007, mid_close=1.1010),
        ]
    )

    records = build_session_records(bars, pair="EURUSD", atr_period=2, extreme_move_atr_multiple=10.0)

    new_york = records.loc[records["session"] == "new_york"].iloc[0]
    asia = records.loc[records["session"] == "asia"].iloc[0]

    assert new_york["fx_session_date"] == pd.Timestamp("2024-01-02")
    assert new_york["directional_efficiency_ratio"] == pytest.approx(1.0)
    assert new_york["close_location_value"] == pytest.approx((1.1004 - 1.0999) / (1.1006 - 1.0999))
    assert asia["continuation_flag"] == 1.0
    assert asia["reversal_flag"] == 0.0


def test_assign_regimes_and_transitions_build_expected_labels() -> None:
    session_records = pd.DataFrame(
        {
            "pair": ["EURUSD"] * 6,
            "session": ["asia", "london", "new_york"] * 2,
            "fx_session_date": pd.to_datetime(
                ["2024-01-02"] * 3 + ["2024-01-03"] * 3
            ),
            "session_start": pd.to_datetime(
                [
                    "2024-01-02 00:00:00+00:00",
                    "2024-01-02 07:00:00+00:00",
                    "2024-01-02 13:00:00+00:00",
                    "2024-01-03 00:00:00+00:00",
                    "2024-01-03 07:00:00+00:00",
                    "2024-01-03 13:00:00+00:00",
                ]
            ),
            "session_end": pd.to_datetime(
                [
                    "2024-01-02 06:45:00+00:00",
                    "2024-01-02 12:45:00+00:00",
                    "2024-01-02 23:45:00+00:00",
                    "2024-01-03 06:45:00+00:00",
                    "2024-01-03 12:45:00+00:00",
                    "2024-01-03 23:45:00+00:00",
                ]
            ),
            "open_price": [1.0] * 6,
            "close_price": [1.01, 1.02, 1.01, 0.99, 0.98, 0.99],
            "high_price": [1.02] * 6,
            "low_price": [0.98] * 6,
            "session_return": [0.01, 0.02, 0.01, -0.01, -0.02, 0.01],
            "session_abs_return": [0.01, 0.02, 0.01, 0.01, 0.02, 0.01],
            "session_range_return": [0.02, 0.03, 0.04, 0.01, 0.025, 0.05],
            "bullish_session": [1, 1, 1, 0, 0, 1],
            "bearish_session": [0, 0, 0, 1, 1, 0],
            "continuation_flag": [1, 1, 1, 1, 1, 0],
            "reversal_flag": [0, 0, 0, 0, 0, 1],
            "realized_vol": [0.001, 0.002, 0.003, 0.004, 0.005, 0.006],
            "sample_bars": [28, 24, 44, 28, 24, 44],
            "initial_bar_return": [0.002] * 6,
            "directional_efficiency_ratio": [0.7, 0.8, 0.6, 0.5, 0.4, 0.3],
            "close_location_value": [0.8, 0.9, 0.75, 0.2, 0.1, 0.6],
            "session_start_bars_since_extreme": [4, 12, 40, 6, 20, 60],
        }
    )

    labeled = assign_regimes(session_records)
    assert set(labeled["volatility_regime"]) <= {"low", "medium", "high"}
    lookup = labeled.set_index(["fx_session_date", "session"])["extreme_regime"]
    assert lookup.loc[(pd.Timestamp("2024-01-02"), "asia")] == "recent_extreme"
    assert lookup.loc[(pd.Timestamp("2024-01-02"), "london")] == "intermediate"
    assert lookup.loc[(pd.Timestamp("2024-01-02"), "new_york")] == "stale"
    assert lookup.loc[(pd.Timestamp("2024-01-03"), "asia")] == "recent_extreme"
    assert lookup.loc[(pd.Timestamp("2024-01-03"), "london")] == "intermediate"
    assert lookup.loc[(pd.Timestamp("2024-01-03"), "new_york")] == "stale"

    transitions = build_transition_records(labeled)
    assert set(transitions["transition"]) == {"asia_to_london", "london_to_new_york"}
    day_two_london_to_ny = transitions.loc[
        (transitions["fx_session_date"] == pd.Timestamp("2024-01-03"))
        & (transitions["transition"] == "london_to_new_york")
    ].iloc[0]
    assert day_two_london_to_ny["reverse_flag"] == 1.0
