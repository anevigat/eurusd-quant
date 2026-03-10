from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy


@dataclass(frozen=True)
class LondonPullbackContinuationConfig:
    timeframe: str
    drift_start_utc: str
    drift_end_utc: str
    entry_start_utc: str
    entry_end_utc: str
    drift_threshold_pips: float
    pullback_mode: str
    atr_period: int
    atr_min_threshold: float
    stop_mode: str
    stop_atr_multiple: float
    exit_model: str
    atr_target_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = True
    allowed_side: str = "both"

    @classmethod
    def from_dict(cls, data: dict) -> "LondonPullbackContinuationConfig":
        return cls(**data)


class LondonPullbackContinuationStrategy(BaseStrategy):
    PIP_SIZE = 0.0001
    EMA_SPAN = 20

    def __init__(self, config: LondonPullbackContinuationConfig) -> None:
        self.config = config
        self._drift_start: time = parse_hhmm(config.drift_start_utc)
        self._drift_end: time = parse_hhmm(config.drift_end_utc)
        self._entry_start: time = parse_hhmm(config.entry_start_utc)
        self._entry_end: time = parse_hhmm(config.entry_end_utc)

        if config.pullback_mode != "ema20":
            raise ValueError("MVP supports only pullback_mode='ema20'")
        if config.stop_mode != "atr":
            raise ValueError("MVP supports only stop_mode='atr'")
        if config.exit_model != "atr_target":
            raise ValueError("MVP supports only exit_model='atr_target'")
        if config.allowed_side not in {"both", "long_only", "short_only"}:
            raise ValueError("allowed_side must be 'both', 'long_only', or 'short_only'")

        self._current_date: date | None = None
        self._traded_today = False

        self._drift_start_close: float | None = None
        self._drift_end_close: float | None = None
        self._bias: str | None = None

        self._long_pullback_touched = False
        self._short_pullback_touched = False
        self._long_touch_seen_at: pd.Timestamp | None = None
        self._short_touch_seen_at: pd.Timestamp | None = None

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []

        self._ema20: float | None = None
        self._ema_alpha = 2.0 / (self.EMA_SPAN + 1.0)

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._traded_today = False
        self._drift_start_close = None
        self._drift_end_close = None
        self._bias = None
        self._long_pullback_touched = False
        self._short_pullback_touched = False
        self._long_touch_seen_at = None
        self._short_touch_seen_at = None

    def _update_atr(self, mid_high: float, mid_low: float, mid_close: float) -> None:
        high_low = mid_high - mid_low
        if self._prev_mid_close is None:
            tr = high_low
        else:
            high_prev_close = abs(mid_high - self._prev_mid_close)
            low_prev_close = abs(mid_low - self._prev_mid_close)
            tr = max(high_low, high_prev_close, low_prev_close)
        self._tr_values.append(tr)
        self._prev_mid_close = mid_close

    def _current_atr(self) -> float:
        if len(self._tr_values) < self.config.atr_period:
            return np.nan
        window = self._tr_values[-self.config.atr_period :]
        return float(np.mean(window))

    def _update_ema20(self, mid_close: float) -> None:
        if self._ema20 is None:
            self._ema20 = mid_close
            return
        self._ema20 = (self._ema_alpha * mid_close) + ((1.0 - self._ema_alpha) * self._ema20)

    def _update_pre_london_drift(self, timestamp: pd.Timestamp, mid_close: float) -> None:
        current_time = timestamp.time()
        if self._drift_start <= current_time <= self._drift_end:
            if self._drift_start_close is None:
                self._drift_start_close = mid_close
            self._drift_end_close = mid_close

    def _resolve_bias(self, timestamp: pd.Timestamp) -> None:
        if self._bias is not None:
            return
        if timestamp.time() < self._entry_start:
            return
        if self._drift_start_close is None or self._drift_end_close is None:
            return

        drift = self._drift_end_close - self._drift_start_close
        threshold = self.config.drift_threshold_pips * self.PIP_SIZE

        if drift >= threshold:
            self._bias = "long"
        elif drift <= -threshold:
            self._bias = "short"
        else:
            self._bias = "none"

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        timestamp: pd.Timestamp = bar["timestamp"]
        bar_day = timestamp.date()
        if self._current_date != bar_day:
            self._reset_day(bar_day)

        mid_close = float(bar["mid_close"])
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])

        self._update_atr(mid_high=mid_high, mid_low=mid_low, mid_close=mid_close)
        self._update_ema20(mid_close=mid_close)
        self._update_pre_london_drift(timestamp=timestamp, mid_close=mid_close)
        self._resolve_bias(timestamp)

        if not in_time_window(timestamp, self._entry_start, self._entry_end):
            return None
        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if self._ema20 is None or self._bias in {None, "none"}:
            return None

        atr = self._current_atr()
        if np.isnan(atr) or atr < self.config.atr_min_threshold:
            return None

        stop_distance = atr * self.config.stop_atr_multiple
        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])

        if self._bias == "long" and self.config.allowed_side != "short_only":
            if mid_low <= self._ema20 and not self._long_pullback_touched:
                self._long_pullback_touched = True
                self._long_touch_seen_at = timestamp
            if (
                self._long_pullback_touched
                and self._long_touch_seen_at is not None
                and timestamp > self._long_touch_seen_at
                and mid_close > self._ema20
            ):
                entry_reference = ask_close
                stop_loss = entry_reference - stop_distance
                take_profit = entry_reference + (atr * self.config.atr_target_multiple)
                if stop_loss < entry_reference and take_profit > entry_reference:
                    self._traded_today = True
                    return Order(
                        symbol="EURUSD",
                        timeframe="15m",
                        side="long",
                        signal_time=timestamp,
                        entry_reference=entry_reference,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        max_holding_bars=self.config.max_holding_bars,
                    )

        if self._bias == "short" and self.config.allowed_side != "long_only":
            if mid_high >= self._ema20 and not self._short_pullback_touched:
                self._short_pullback_touched = True
                self._short_touch_seen_at = timestamp
            if (
                self._short_pullback_touched
                and self._short_touch_seen_at is not None
                and timestamp > self._short_touch_seen_at
                and mid_close < self._ema20
            ):
                entry_reference = bid_close
                stop_loss = entry_reference + stop_distance
                take_profit = entry_reference - (atr * self.config.atr_target_multiple)
                if stop_loss > entry_reference and take_profit < entry_reference:
                    self._traded_today = True
                    return Order(
                        symbol="EURUSD",
                        timeframe="15m",
                        side="short",
                        signal_time=timestamp,
                        entry_reference=entry_reference,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        max_holding_bars=self.config.max_holding_bars,
                    )

        return None
