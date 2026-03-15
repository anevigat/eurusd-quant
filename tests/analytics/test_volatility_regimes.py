from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.analytics.volatility_regimes import (
    assign_time_aware_volatility_regimes,
    compute_session_step_forward_returns,
    summarize_regime_persistence,
    summarize_regime_transition_matrix,
)


def _session_row(ts: str, *, pair: str, realized_vol: float, close_price: float, session_return: float, regime_extra: float = 0.0) -> dict[str, object]:
    open_price = close_price / (1.0 + session_return)
    return {
        "pair": pair,
        "session": "london",
        "fx_session_date": pd.Timestamp(ts, tz="UTC").normalize(),
        "session_start": pd.Timestamp(ts, tz="UTC"),
        "session_end": pd.Timestamp(ts, tz="UTC") + pd.Timedelta(hours=6),
        "open_price": open_price,
        "close_price": close_price,
        "high_price": max(open_price, close_price) + 0.001 + regime_extra,
        "low_price": min(open_price, close_price) - 0.001,
        "session_return": session_return,
        "session_abs_return": abs(session_return),
        "session_range_return": 0.002 + regime_extra,
        "bullish_session": float(session_return > 0),
        "bearish_session": float(session_return < 0),
        "continuation_flag": 1.0,
        "reversal_flag": 0.0,
        "realized_vol": realized_vol,
        "sample_bars": 24,
        "initial_bar_return": session_return / 4.0,
        "directional_efficiency_ratio": 0.2 + regime_extra,
        "close_location_value": 0.55,
        "session_start_bars_since_extreme": 12.0,
    }


def test_assign_time_aware_volatility_regimes_uses_only_history() -> None:
    records = pd.DataFrame(
        [
            _session_row("2024-01-01 07:00:00", pair="EURUSD", realized_vol=0.10, close_price=1.0, session_return=0.01),
            _session_row("2024-01-02 07:00:00", pair="EURUSD", realized_vol=0.20, close_price=1.0, session_return=0.01),
            _session_row("2024-01-03 07:00:00", pair="EURUSD", realized_vol=0.30, close_price=1.0, session_return=0.01),
            _session_row("2024-01-04 07:00:00", pair="EURUSD", realized_vol=0.40, close_price=1.0, session_return=0.01),
            _session_row("2024-01-05 07:00:00", pair="EURUSD", realized_vol=0.15, close_price=1.0, session_return=0.01),
            _session_row("2024-01-06 07:00:00", pair="EURUSD", realized_vol=0.35, close_price=1.0, session_return=0.01),
        ]
    )

    labeled = assign_time_aware_volatility_regimes(
        records,
        lookback_sessions=4,
        min_history=3,
        low_quantile=1 / 3,
        high_quantile=2 / 3,
    )

    assert list(labeled["volatility_regime"][:3]) == ["unknown", "unknown", "unknown"]
    assert labeled.iloc[3]["volatility_regime"] == "high_vol"
    assert labeled.iloc[4]["volatility_regime"] == "low_vol"
    assert labeled.iloc[5]["volatility_regime"] == "high_vol"


def test_compute_session_step_forward_returns_is_pair_local() -> None:
    records = pd.DataFrame(
        [
            _session_row("2024-01-01 07:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.00, session_return=0.00),
            _session_row("2024-01-02 07:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.02, session_return=0.00),
            _session_row("2024-01-01 07:00:00", pair="GBPUSD", realized_vol=0.1, close_price=2.00, session_return=0.00),
        ]
    )

    forward = compute_session_step_forward_returns(records, horizons=(1,))

    eurusd_first = forward.loc[(forward["pair"] == "EURUSD")].iloc[0]
    gbpusd_only = forward.loc[(forward["pair"] == "GBPUSD")].iloc[0]
    assert eurusd_first["forward_return_1"] == pytest.approx(0.02)
    assert pd.isna(gbpusd_only["forward_return_1"])


def test_persistence_and_transition_summary_capture_runs() -> None:
    records = pd.DataFrame(
        [
            _session_row("2024-01-01 00:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.00, session_return=0.00),
            _session_row("2024-01-02 00:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.01, session_return=0.00),
            _session_row("2024-01-03 00:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.02, session_return=0.00),
            _session_row("2024-01-04 00:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.03, session_return=0.00),
            _session_row("2024-01-05 00:00:00", pair="EURUSD", realized_vol=0.1, close_price=1.04, session_return=0.00),
        ]
    )
    records["volatility_regime"] = pd.Categorical(
        ["low_vol", "low_vol", "high_vol", "high_vol", "low_vol"],
        categories=["unknown", "low_vol", "medium_vol", "high_vol"],
        ordered=True,
    )

    persistence = summarize_regime_persistence(records)
    low_row = persistence.loc[persistence["volatility_regime"] == "low_vol"].iloc[0]
    high_row = persistence.loc[persistence["volatility_regime"] == "high_vol"].iloc[0]
    assert low_row["run_count"] == 2
    assert low_row["avg_duration_sessions"] == pytest.approx(1.5)
    assert high_row["run_count"] == 1
    assert high_row["avg_duration_sessions"] == pytest.approx(2.0)

    matrix = summarize_regime_transition_matrix(records)
    eurusd = matrix.loc[matrix["pair"] == "EURUSD"]
    low_to_low = eurusd.loc[(eurusd["from_regime"] == "low_vol") & (eurusd["to_regime"] == "low_vol")].iloc[0]
    low_to_high = eurusd.loc[(eurusd["from_regime"] == "low_vol") & (eurusd["to_regime"] == "high_vol")].iloc[0]
    assert low_to_low["transition_count"] == 1
    assert low_to_high["transition_count"] == 1
    assert low_to_low["sample_count"] == 2
    assert low_to_low["transition_probability"] == pytest.approx(0.5)
