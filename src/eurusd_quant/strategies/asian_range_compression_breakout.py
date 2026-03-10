from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy


@dataclass(frozen=True)
class AsianRangeCompressionBreakoutConfig:
    timeframe: str
    asian_start_utc: str
    asian_end_utc: str
    entry_start_utc: str
    entry_end_utc: str
    atr_period: int
    compression_atr_ratio: float
    breakout_buffer_pips: float
    stop_atr_multiple: float
    exit_model: str
    atr_target_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "AsianRangeCompressionBreakoutConfig":
        return cls(**data)


class AsianRangeCompressionBreakoutStrategy(BaseStrategy):
    PIP_SIZE = 0.0001

    def __init__(self, config: AsianRangeCompressionBreakoutConfig) -> None:
        self.config = config
        self._asian_start: time = parse_hhmm(config.asian_start_utc)
        self._asian_end: time = parse_hhmm(config.asian_end_utc)
        self._entry_start: time = parse_hhmm(config.entry_start_utc)
        self._entry_end: time = parse_hhmm(config.entry_end_utc)
        if config.exit_model != "atr_target":
            raise ValueError("MVP supports only exit_model='atr_target'")

        self._current_date: date | None = None
        self._asian_high: float | None = None
        self._asian_low: float | None = None
        self._asian_bars: int = 0
        self._traded_today = False

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []

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

    def _update_asian_range(self, bar: pd.Series, timestamp: pd.Timestamp) -> None:
        if not in_time_window(timestamp, self._asian_start, self._asian_end):
            return
        bid_high = float(bar["bid_high"])
        ask_low = float(bar["ask_low"])
        self._asian_high = bid_high if self._asian_high is None else max(self._asian_high, bid_high)
        self._asian_low = ask_low if self._asian_low is None else min(self._asian_low, ask_low)
        self._asian_bars += 1

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
        self._update_asian_range(bar, timestamp)

        if not in_time_window(timestamp, self._entry_start, self._entry_end):
            return None
        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if self._asian_bars == 0 or self._asian_high is None or self._asian_low is None:
            return None

        atr = self._current_atr()
        if np.isnan(atr) or atr <= 0.0:
            return None

        asian_range = self._asian_high - self._asian_low
        compression_threshold = self.config.compression_atr_ratio * atr
        if asian_range >= compression_threshold:
            return None

        breakout_buffer = self.config.breakout_buffer_pips * self.PIP_SIZE
        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.atr_target_multiple

        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])

        if bid_close > (self._asian_high + breakout_buffer):
            self._traded_today = True
            entry_reference = ask_close
            return Order(
                symbol="EURUSD",
                timeframe="15m",
                side="long",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=entry_reference - stop_distance,
                take_profit=entry_reference + target_distance,
                max_holding_bars=self.config.max_holding_bars,
            )

        if ask_close < (self._asian_low - breakout_buffer):
            self._traded_today = True
            entry_reference = bid_close
            return Order(
                symbol="EURUSD",
                timeframe="15m",
                side="short",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=entry_reference + stop_distance,
                take_profit=entry_reference - target_distance,
                max_holding_bars=self.config.max_holding_bars,
            )

        return None
