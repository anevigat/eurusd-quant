from __future__ import annotations

from collections import deque
from datetime import date

import pandas as pd
import pytest

from eurusd_quant.strategies.h1_downside_continuation import (
    H1DownsideContinuationConfig,
    H1DownsideContinuationStrategy,
)


def _config(
    *,
    experiment_id: str = "EXP_H1A_01",
    session_context: str = "london",
    entry_style: str = "breach_bar_close",
    allowed_event_types: list[str] | None = None,
    allowed_magnitude_buckets: list[str] | None = None,
    magnitude_history_min_events: int = 10,
    range_history_min_sessions: int = 20,
) -> H1DownsideContinuationConfig:
    return H1DownsideContinuationConfig(
        timeframe="15m",
        experiment_id=experiment_id,
        pair_scope=["EURUSD", "GBPUSD"],
        session_context=session_context,
        entry_style=entry_style,
        allowed_event_types=allowed_event_types or ["breakout_low", "sweep_low"],
        allowed_magnitude_buckets=allowed_magnitude_buckets or ["small", "medium"],
        structural_lookback_windows=[24, 48, 96],
        atr_period=3,
        range_baseline_lookback_sessions=20,
        range_history_min_sessions=range_history_min_sessions,
        magnitude_history_min_events=magnitude_history_min_events,
        expansion_ratio_threshold=1.2,
        expansion_percentile_threshold=2 / 3,
        stop_buffer_atr_multiple=0.25,
        fail_safe_take_profit_atr_multiple=20.0,
        max_holding_bars=16,
        one_trade_per_session=True,
    )


def _bar(
    ts: str,
    *,
    mid_open: float,
    mid_high: float,
    mid_low: float,
    mid_close: float,
    symbol: str = "EURUSD",
    spread: float = 0.0001,
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
            "bid_open": mid_open - half,
            "bid_high": mid_high - half,
            "bid_low": mid_low - half,
            "bid_close": mid_close - half,
            "ask_open": mid_open + half,
            "ask_high": mid_high + half,
            "ask_low": mid_low + half,
            "ask_close": mid_close + half,
        }
    )


def _prime_strategy(
    strategy: H1DownsideContinuationStrategy,
    *,
    session_label: str = "london",
    fx_session_date: date = date(2024, 1, 2),
    current_session_high: float = 1.1022,
    current_session_low: float = 1.1008,
    current_session_bar_index: int = 5,
    breakout_history: list[float] | None = None,
    sweep_history: list[float] | None = None,
) -> None:
    strategy._current_session_label = session_label
    strategy._current_fx_session_date = fx_session_date
    strategy._current_session_high = current_session_high
    strategy._current_session_low = current_session_low
    strategy._current_session_bar_index = current_session_bar_index
    strategy._session_ranges_by_label[session_label] = deque([0.0008] * 30, maxlen=200)
    strategy._mid_low_history = deque([1.1000] * 96, maxlen=96)
    strategy._mid_high_history = deque([1.1015] * 96, maxlen=96)
    strategy._tr_values = deque([0.0010, 0.0010, 0.0010], maxlen=3)
    strategy._prev_mid_close = 1.1009
    strategy._magnitude_history_by_event_type["breakout_low"] = deque(
        breakout_history or [0.30, 0.36, 0.42, 0.48, 0.54, 0.60, 0.66, 0.72, 0.78, 0.84],
        maxlen=500,
    )
    strategy._magnitude_history_by_event_type["sweep_low"] = deque(
        sweep_history or [0.18, 0.22, 0.26, 0.30, 0.34, 0.38, 0.42, 0.46, 0.50, 0.54],
        maxlen=500,
    )


def test_breakout_low_in_london_generates_short_for_h1a() -> None:
    strategy = H1DownsideContinuationStrategy(_config())
    _prime_strategy(strategy)

    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1009,
            mid_high=1.1011,
            mid_low=1.0995,
            mid_close=1.0997,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is not None
    assert order.side == "short"
    assert order.symbol == "EURUSD"
    assert order.max_holding_bars == 16


def test_sweep_low_routes_only_to_h1b_context() -> None:
    strategy = H1DownsideContinuationStrategy(
        _config(
            experiment_id="EXP_H1B_01",
            session_context="early_new_york",
            allowed_event_types=["sweep_low"],
            allowed_magnitude_buckets=["medium"],
        )
    )
    _prime_strategy(
        strategy,
        session_label="new_york",
        current_session_high=1.1020,
        current_session_low=1.1008,
        current_session_bar_index=3,
    )

    order = strategy.generate_order(
        _bar(
            "2024-01-02 13:45:00",
            mid_open=1.1008,
            mid_high=1.1010,
            mid_low=1.0996,
            mid_close=1.1002,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is not None
    assert order.side == "short"


def test_session_context_filter_blocks_london_signal_for_h1b() -> None:
    strategy = H1DownsideContinuationStrategy(
        _config(
            experiment_id="EXP_H1B_01",
            session_context="early_new_york",
            allowed_event_types=["sweep_low"],
            allowed_magnitude_buckets=["medium"],
        )
    )
    _prime_strategy(strategy, session_label="london")

    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1008,
            mid_high=1.1010,
            mid_low=1.0996,
            mid_close=1.1002,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is None


def test_strongly_expanded_gate_blocks_signal_when_session_range_is_normal() -> None:
    strategy = H1DownsideContinuationStrategy(_config())
    _prime_strategy(strategy)
    strategy._session_ranges_by_label["london"] = deque([0.0020] * 30, maxlen=200)
    strategy._current_session_high = 1.1010
    strategy._current_session_low = 1.1005

    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1007,
            mid_high=1.1009,
            mid_low=1.0995,
            mid_close=1.0997,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is None


def test_magnitude_bucket_filter_blocks_small_event_for_h1b() -> None:
    strategy = H1DownsideContinuationStrategy(
        _config(
            experiment_id="EXP_H1B_01",
            session_context="early_new_york",
            allowed_event_types=["sweep_low"],
            allowed_magnitude_buckets=["medium"],
        )
    )
    _prime_strategy(
        strategy,
        session_label="new_york",
        current_session_bar_index=3,
        sweep_history=[0.24, 0.28, 0.32, 0.36, 0.40, 0.44, 0.48, 0.52, 0.56, 0.60],
    )

    order = strategy.generate_order(
        _bar(
            "2024-01-02 13:45:00",
            mid_open=1.1007,
            mid_high=1.1008,
            mid_low=1.0998,
            mid_close=1.1002,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is None


def test_one_bar_confirmation_waits_for_next_bar() -> None:
    strategy = H1DownsideContinuationStrategy(
        _config(
            experiment_id="EXP_H1A_02",
            entry_style="one_bar_confirmation",
        )
    )
    _prime_strategy(strategy)

    first_order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1009,
            mid_high=1.1011,
            mid_low=1.0995,
            mid_close=1.0997,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert first_order is None
    assert strategy._pending_confirmation is not None

    confirmed_order = strategy.generate_order(
        _bar(
            "2024-01-02 08:15:00",
            mid_open=1.0998,
            mid_high=1.1000,
            mid_low=1.0992,
            mid_close=1.0994,
        ),
        has_open_position=False,
        has_pending_order=False,
    )
    assert confirmed_order is not None
    assert confirmed_order.side == "short"


def test_no_lookahead_magnitude_history_requires_prior_events() -> None:
    strategy = H1DownsideContinuationStrategy(_config(magnitude_history_min_events=11))
    _prime_strategy(
        strategy,
        breakout_history=[0.30, 0.36, 0.42, 0.48, 0.54, 0.60, 0.66, 0.72, 0.78, 0.84],
    )

    order = strategy.generate_order(
        _bar(
            "2024-01-02 08:00:00",
            mid_open=1.1009,
            mid_high=1.1011,
            mid_low=1.0995,
            mid_close=1.0997,
        ),
        has_open_position=False,
        has_pending_order=False,
    )

    assert order is None


def test_invalid_parameter_handling_rejects_unsupported_entry_style() -> None:
    with pytest.raises(ValueError, match="entry_style"):
        H1DownsideContinuationStrategy(
            _config(entry_style="next_bar_open")
        )
