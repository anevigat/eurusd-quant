from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy


@dataclass(frozen=True)
class SessionBreakoutConfig:
    timeframe: str
    asian_range_start_utc: str
    asian_range_end_utc: str
    entry_start_utc: str
    entry_end_utc: str
    atr_period: int
    atr_min_threshold: float
    stop_atr_multiple: float
    take_profit_r: float
    max_holding_bars: int

    @classmethod
    def from_dict(cls, data: dict) -> "SessionBreakoutConfig":
        return cls(**data)


class SessionRangeBreakoutStrategy(BaseStrategy):
    def __init__(self, config: SessionBreakoutConfig) -> None:
        self.config = config
        self._asian_start: time = parse_hhmm(config.asian_range_start_utc)
        self._asian_end: time = parse_hhmm(config.asian_range_end_utc)
        self._entry_start: time = parse_hhmm(config.entry_start_utc)
        self._entry_end: time = parse_hhmm(config.entry_end_utc)

        self._current_date: date | None = None
        self._asian_high: float | None = None
        self._asian_low: float | None = None
        self._asian_bars: int = 0
        self._traded_today = False

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []

    @property
    def current_asian_high(self) -> float | None:
        return self._asian_high

    @property
    def current_asian_low(self) -> float | None:
        return self._asian_low

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._asian_high = None
        self._asian_low = None
        self._asian_bars = 0
        self._traded_today = False

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

        self._update_atr(
            mid_high=float(bar["mid_high"]),
            mid_low=float(bar["mid_low"]),
            mid_close=float(bar["mid_close"]),
        )

        if in_time_window(timestamp, self._asian_start, self._asian_end):
            bid_high = float(bar["bid_high"])
            ask_low = float(bar["ask_low"])
            self._asian_high = bid_high if self._asian_high is None else max(self._asian_high, bid_high)
            self._asian_low = ask_low if self._asian_low is None else min(self._asian_low, ask_low)
            self._asian_bars += 1

        if not in_time_window(timestamp, self._entry_start, self._entry_end):
            return None

        if self._asian_bars == 0 or self._asian_high is None or self._asian_low is None:
            return None

        if self._traded_today or has_open_position or has_pending_order:
            return None

        atr = self._current_atr()
        if np.isnan(atr) or atr < self.config.atr_min_threshold:
            return None

        stop_distance = atr * self.config.stop_atr_multiple
        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])

        if bid_close > self._asian_high:
            self._traded_today = True
            entry_reference = ask_close
            stop_loss = entry_reference - stop_distance
            take_profit = entry_reference + (stop_distance * self.config.take_profit_r)
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

        if ask_close < self._asian_low:
            self._traded_today = True
            entry_reference = bid_close
            stop_loss = entry_reference + stop_distance
            take_profit = entry_reference - (stop_distance * self.config.take_profit_r)
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
