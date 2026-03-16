from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from eurusd_quant.analytics.session_structure import label_session
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


FX_SESSION_ROLLOVER_HOUR_UTC = 22
SESSION_BAR_COUNTS = {
    "asia": 28,
    "london": 24,
    "new_york": 44,
}
ALLOWED_PAIRS = {"EURUSD", "GBPUSD"}
ALLOWED_EVENT_TYPES = {"breakout_low", "sweep_low"}
ALLOWED_MAGNITUDE_BUCKETS = {"small", "medium", "large"}
ALLOWED_SESSION_CONTEXTS = {"london", "early_new_york"}
ALLOWED_ENTRY_STYLES = {"breach_bar_close", "one_bar_confirmation"}


@dataclass(frozen=True)
class H1DownsideContinuationConfig:
    timeframe: str
    experiment_id: str
    pair_scope: list[str]
    session_context: str
    entry_style: str
    allowed_event_types: list[str]
    allowed_magnitude_buckets: list[str]
    structural_lookback_windows: list[int]
    atr_period: int = 14
    range_baseline_lookback_sessions: int = 20
    range_history_min_sessions: int = 20
    magnitude_history_min_events: int = 20
    expansion_ratio_threshold: float = 1.2
    expansion_percentile_threshold: float = 2 / 3
    stop_buffer_atr_multiple: float = 0.25
    fail_safe_take_profit_atr_multiple: float = 20.0
    max_holding_bars: int = 16
    one_trade_per_session: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "H1DownsideContinuationConfig":
        return cls(**data)


@dataclass(frozen=True)
class H1SignalCandidate:
    event_type: str
    lookback_window: int
    breach_reference_low: float
    breach_bar_high: float
    breach_close: float
    breach_magnitude_atr: float
    magnitude_bucket: str
    signal_time: pd.Timestamp


class H1DownsideContinuationStrategy(BaseStrategy):
    def __init__(self, config: H1DownsideContinuationConfig) -> None:
        self.config = config
        self._validate_config()

        self._pair_scope = {normalize_symbol(pair) for pair in config.pair_scope}
        self._max_window = max(config.structural_lookback_windows)

        self._prev_mid_close: float | None = None
        self._tr_values: deque[float] = deque(maxlen=config.atr_period)
        self._mid_high_history: deque[float] = deque(maxlen=self._max_window)
        self._mid_low_history: deque[float] = deque(maxlen=self._max_window)

        self._current_fx_session_date: date | None = None
        self._current_session_label: str | None = None
        self._current_session_high: float | None = None
        self._current_session_low: float | None = None
        self._current_session_bar_index: int = 0
        self._traded_current_session = False
        self._session_ranges_by_label: dict[str, deque[float]] = {
            "asia": deque(maxlen=max(200, config.range_baseline_lookback_sessions * 5)),
            "london": deque(maxlen=max(200, config.range_baseline_lookback_sessions * 5)),
            "new_york": deque(maxlen=max(200, config.range_baseline_lookback_sessions * 5)),
        }
        self._magnitude_history_by_event_type: dict[str, deque[float]] = {
            "breakout_low": deque(maxlen=500),
            "sweep_low": deque(maxlen=500),
        }
        self._pending_confirmation: H1SignalCandidate | None = None

    def _coerce_timestamp(self, value: Any) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _validate_config(self) -> None:
        if self.config.timeframe != "15m":
            raise ValueError("H1 downside continuation MVP supports only timeframe='15m'")
        if self.config.session_context not in ALLOWED_SESSION_CONTEXTS:
            raise ValueError(f"session_context must be one of {sorted(ALLOWED_SESSION_CONTEXTS)}")
        if self.config.entry_style not in ALLOWED_ENTRY_STYLES:
            raise ValueError(f"entry_style must be one of {sorted(ALLOWED_ENTRY_STYLES)}")
        if not self.config.pair_scope:
            raise ValueError("pair_scope must not be empty")
        normalized_scope = {normalize_symbol(pair) for pair in self.config.pair_scope}
        unsupported_pairs = normalized_scope.difference(ALLOWED_PAIRS)
        if unsupported_pairs:
            raise ValueError(f"Unsupported pair_scope values: {sorted(unsupported_pairs)}")
        event_types = set(self.config.allowed_event_types)
        if not event_types:
            raise ValueError("allowed_event_types must not be empty")
        unsupported_events = event_types.difference(ALLOWED_EVENT_TYPES)
        if unsupported_events:
            raise ValueError(f"Unsupported allowed_event_types: {sorted(unsupported_events)}")
        magnitude_buckets = set(self.config.allowed_magnitude_buckets)
        if not magnitude_buckets:
            raise ValueError("allowed_magnitude_buckets must not be empty")
        unsupported_buckets = magnitude_buckets.difference(ALLOWED_MAGNITUDE_BUCKETS)
        if unsupported_buckets:
            raise ValueError(f"Unsupported allowed_magnitude_buckets: {sorted(unsupported_buckets)}")
        if not self.config.structural_lookback_windows:
            raise ValueError("structural_lookback_windows must not be empty")
        if any(window <= 1 for window in self.config.structural_lookback_windows):
            raise ValueError("structural_lookback_windows values must be > 1")
        if self.config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if self.config.range_baseline_lookback_sessions < 5:
            raise ValueError("range_baseline_lookback_sessions must be >= 5")
        if self.config.range_history_min_sessions < self.config.range_baseline_lookback_sessions:
            raise ValueError("range_history_min_sessions must be >= range_baseline_lookback_sessions")
        if self.config.magnitude_history_min_events < 10:
            raise ValueError("magnitude_history_min_events must be >= 10")
        if self.config.expansion_ratio_threshold <= 1.0:
            raise ValueError("expansion_ratio_threshold must be > 1.0")
        if not 0.0 < self.config.expansion_percentile_threshold < 1.0:
            raise ValueError("expansion_percentile_threshold must be between 0 and 1")
        if self.config.stop_buffer_atr_multiple < 0.0:
            raise ValueError("stop_buffer_atr_multiple must be >= 0")
        if self.config.fail_safe_take_profit_atr_multiple <= 0.0:
            raise ValueError("fail_safe_take_profit_atr_multiple must be > 0")
        if self.config.max_holding_bars <= 0:
            raise ValueError("max_holding_bars must be > 0")

    @property
    def current_session_label(self) -> str | None:
        return self._current_session_label

    @property
    def current_session_bar_index(self) -> int:
        return self._current_session_bar_index

    @property
    def current_session_range(self) -> float | None:
        if self._current_session_high is None or self._current_session_low is None:
            return None
        return self._current_session_high - self._current_session_low

    def _compute_fx_session_date(self, timestamp: pd.Timestamp) -> date:
        shifted = self._coerce_timestamp(timestamp) + pd.Timedelta(hours=24 - FX_SESSION_ROLLOVER_HOUR_UTC)
        return shifted.date()

    def _finalize_previous_session(self) -> None:
        if (
            self._current_session_label is None
            or self._current_session_high is None
            or self._current_session_low is None
        ):
            return
        completed_range = self._current_session_high - self._current_session_low
        self._session_ranges_by_label[self._current_session_label].append(float(completed_range))

    def _reset_session_state(self, session_label: str, fx_session_date: date) -> None:
        self._current_fx_session_date = fx_session_date
        self._current_session_label = session_label
        self._current_session_high = None
        self._current_session_low = None
        self._current_session_bar_index = 0
        self._traded_current_session = False
        self._pending_confirmation = None

    def _update_session_state(self, bar: pd.Series) -> tuple[str, date]:
        timestamp = self._coerce_timestamp(bar["timestamp"])
        session_label = label_session(timestamp)
        fx_session_date = self._compute_fx_session_date(timestamp)
        if session_label != self._current_session_label or fx_session_date != self._current_fx_session_date:
            self._finalize_previous_session()
            self._reset_session_state(session_label, fx_session_date)

        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        self._current_session_high = (
            mid_high if self._current_session_high is None else max(self._current_session_high, mid_high)
        )
        self._current_session_low = (
            mid_low if self._current_session_low is None else min(self._current_session_low, mid_low)
        )
        session_bar_index = self._current_session_bar_index
        self._current_session_bar_index += 1
        return session_label, fx_session_date

    def _update_atr(self, bar: pd.Series) -> float | None:
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        high_low = mid_high - mid_low
        if self._prev_mid_close is None:
            tr = high_low
        else:
            tr = max(
                high_low,
                abs(mid_high - self._prev_mid_close),
                abs(mid_low - self._prev_mid_close),
            )
        self._tr_values.append(float(tr))
        self._prev_mid_close = float(bar["mid_close"])
        if len(self._tr_values) < self.config.atr_period:
            return None
        return float(np.mean(self._tr_values))

    def _is_allowed_session_context(self, session_label: str, session_bar_index: int) -> bool:
        if self.config.session_context == "london":
            return session_label == "london"
        early_new_york_bars = SESSION_BAR_COUNTS["new_york"] // 3 + 1
        return session_label == "new_york" and session_bar_index < early_new_york_bars

    def _is_strongly_expanded(self) -> bool:
        current_range = self.current_session_range
        session_label = self._current_session_label
        if current_range is None or session_label is None or current_range <= 0:
            return False
        history = list(self._session_ranges_by_label[session_label])
        if len(history) < self.config.range_history_min_sessions:
            return False
        baseline_window = history[-self.config.range_baseline_lookback_sessions :]
        baseline_median = float(np.median(baseline_window))
        if baseline_median <= 0:
            return False
        range_ratio = current_range / baseline_median
        percentile = float(np.mean(np.asarray(baseline_window, dtype=float) <= current_range))
        return (
            range_ratio >= self.config.expansion_ratio_threshold
            and percentile >= self.config.expansion_percentile_threshold
        )

    def _classify_magnitude_bucket(self, event_type: str, magnitude_atr: float) -> str:
        history = list(self._magnitude_history_by_event_type[event_type])
        if len(history) < self.config.magnitude_history_min_events:
            return "unknown"
        values = np.asarray(history, dtype=float)
        q1 = float(np.quantile(values, 1 / 3))
        q2 = float(np.quantile(values, 2 / 3))
        if q1 == q2:
            return "medium"
        if magnitude_atr <= q1:
            return "small"
        if magnitude_atr <= q2:
            return "medium"
        return "large"

    def _detect_candidate_events(
        self,
        bar: pd.Series,
        *,
        atr: float,
    ) -> list[H1SignalCandidate]:
        if len(self._mid_low_history) < self._max_window:
            return []

        candidates: list[H1SignalCandidate] = []
        mid_low = float(bar["mid_low"])
        mid_high = float(bar["mid_high"])
        mid_close = float(bar["mid_close"])
        timestamp = self._coerce_timestamp(bar["timestamp"])

        low_history = list(self._mid_low_history)
        for window in self.config.structural_lookback_windows:
            prior_low = float(min(low_history[-window:]))
            if mid_low >= prior_low:
                continue
            event_type = "sweep_low" if mid_close > prior_low else "breakout_low"
            if event_type not in self.config.allowed_event_types:
                continue
            breach_magnitude_atr = (prior_low - mid_low) / atr if atr > 0 else np.nan
            if not np.isfinite(breach_magnitude_atr) or breach_magnitude_atr <= 0:
                continue
            magnitude_bucket = self._classify_magnitude_bucket(event_type, float(breach_magnitude_atr))
            if magnitude_bucket not in self.config.allowed_magnitude_buckets:
                continue
            candidates.append(
                H1SignalCandidate(
                    event_type=event_type,
                    lookback_window=window,
                    breach_reference_low=prior_low,
                    breach_bar_high=mid_high,
                    breach_close=mid_close,
                    breach_magnitude_atr=float(breach_magnitude_atr),
                    magnitude_bucket=magnitude_bucket,
                    signal_time=timestamp,
                )
            )
        return candidates

    def _update_magnitude_history(self, bar: pd.Series, *, atr: float) -> None:
        if len(self._mid_low_history) < self._max_window or atr <= 0:
            return
        mid_low = float(bar["mid_low"])
        mid_close = float(bar["mid_close"])
        low_history = list(self._mid_low_history)
        for window in self.config.structural_lookback_windows:
            prior_low = float(min(low_history[-window:]))
            if mid_low >= prior_low:
                continue
            event_type = "sweep_low" if mid_close > prior_low else "breakout_low"
            magnitude_atr = (prior_low - mid_low) / atr
            if np.isfinite(magnitude_atr) and magnitude_atr > 0:
                self._magnitude_history_by_event_type[event_type].append(float(magnitude_atr))

    def _build_short_order(self, bar: pd.Series, candidate: H1SignalCandidate, *, atr: float) -> Order | None:
        if atr <= 0:
            return None
        symbol = normalize_symbol(str(bar["symbol"]))
        entry_reference = float(bar["bid_close"])
        stop_loss = float(bar["ask_high"]) + (atr * self.config.stop_buffer_atr_multiple)
        take_profit = entry_reference - (atr * self.config.fail_safe_take_profit_atr_multiple)
        if stop_loss <= entry_reference or take_profit >= entry_reference:
            return None
        self._traded_current_session = True
        return Order(
            symbol=symbol,
            timeframe=self.config.timeframe,
            side="short",
            signal_time=self._coerce_timestamp(bar["timestamp"]),
            entry_reference=entry_reference,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_holding_bars=self.config.max_holding_bars,
        )

    def _handle_confirmation(
        self,
        bar: pd.Series,
        *,
        atr: float,
        session_label: str,
        session_bar_index: int,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        candidate = self._pending_confirmation
        if candidate is None:
            return None

        # Confirmation is evaluated on exactly the next bar; then the candidate is cleared.
        self._pending_confirmation = None
        if has_open_position or has_pending_order or self._traded_current_session:
            return None
        if not self._is_allowed_session_context(session_label, session_bar_index):
            return None
        if not self._is_strongly_expanded():
            return None
        if float(bar["mid_close"]) >= candidate.breach_close:
            return None
        return self._build_short_order(bar, candidate, atr=atr)

    def _select_best_candidate(self, candidates: list[H1SignalCandidate]) -> H1SignalCandidate | None:
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (item.breach_magnitude_atr, item.lookback_window, item.event_type),
        )

    def _append_price_history(self, bar: pd.Series) -> None:
        self._mid_high_history.append(float(bar["mid_high"]))
        self._mid_low_history.append(float(bar["mid_low"]))

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        symbol = normalize_symbol(str(bar["symbol"]))
        if symbol not in self._pair_scope:
            raise ValueError(f"{self.config.experiment_id} received unsupported symbol '{symbol}'")

        session_label, _ = self._update_session_state(bar)
        session_bar_index = self._current_session_bar_index - 1
        atr = self._update_atr(bar)

        order: Order | None = None
        if self.config.entry_style == "one_bar_confirmation" and atr is not None:
            order = self._handle_confirmation(
                bar,
                atr=atr,
                session_label=session_label,
                session_bar_index=session_bar_index,
                has_open_position=has_open_position,
                has_pending_order=has_pending_order,
            )

        if order is None and atr is not None:
            can_signal = (
                not has_open_position
                and not has_pending_order
                and (not self.config.one_trade_per_session or not self._traded_current_session)
                and self._is_allowed_session_context(session_label, session_bar_index)
                and self._is_strongly_expanded()
            )
            if can_signal:
                candidates = self._detect_candidate_events(bar, atr=atr)
                selected = self._select_best_candidate(candidates)
                if selected is not None:
                    if self.config.entry_style == "breach_bar_close":
                        order = self._build_short_order(bar, selected, atr=atr)
                    else:
                        self._pending_confirmation = selected

        if atr is not None:
            self._update_magnitude_history(bar, atr=atr)
        self._append_price_history(bar)
        return order
