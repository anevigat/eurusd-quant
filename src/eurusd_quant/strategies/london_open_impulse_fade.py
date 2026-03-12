from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


def _minutes_since_midnight(value: time) -> int:
    return value.hour * 60 + value.minute


@dataclass(frozen=True)
class LondonOpenImpulseFadeConfig:
    timeframe: str
    atr_period: int
    session_start_utc: str
    session_end_utc: str
    impulse_bars: int
    impulse_threshold_atr: float
    stop_atr_multiple: float
    target_atr_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "LondonOpenImpulseFadeConfig":
        return cls(**data)


class LondonOpenImpulseFadeStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"
    BAR_MINUTES = 15

    def __init__(self, config: LondonOpenImpulseFadeConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.impulse_bars < 1:
            raise ValueError("impulse_bars must be >= 1")
        if config.impulse_threshold_atr <= 0:
            raise ValueError("impulse_threshold_atr must be > 0")
        if config.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be > 0")
        if config.target_atr_multiple <= 0:
            raise ValueError("target_atr_multiple must be > 0")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")

        self._session_start = parse_hhmm(config.session_start_utc)
        self._session_end = parse_hhmm(config.session_end_utc)
        self._session_start_minute = _minutes_since_midnight(self._session_start)
        self._session_end_minute = _minutes_since_midnight(self._session_end)
        if self._session_end_minute <= self._session_start_minute:
            raise ValueError("session_end_utc must be after session_start_utc")

        self._impulse_end_minute = self._session_start_minute + (config.impulse_bars * self.BAR_MINUTES)
        if self._impulse_end_minute >= self._session_end_minute:
            raise ValueError("impulse_bars window must be smaller than the full session window")

        self._current_date: date | None = None
        self._traded_today = False
        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []
        self._atr: float | None = None

        self._impulse_open: float | None = None
        self._impulse_close: float | None = None
        self._impulse_high: float | None = None
        self._impulse_low: float | None = None
        self._impulse_count = 0

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._traded_today = False
        self._prev_mid_close = None
        self._tr_values = []
        self._atr = None
        self._impulse_open = None
        self._impulse_close = None
        self._impulse_high = None
        self._impulse_low = None
        self._impulse_count = 0

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        symbol = normalize_symbol(str(raw_symbol))
        if not symbol:
            return self.DEFAULT_SYMBOL
        return symbol

    def _update_atr(self, bar: pd.Series, prev_mid_close: float | None) -> float:
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        if prev_mid_close is None:
            tr = mid_high - mid_low
        else:
            tr = max(
                mid_high - mid_low,
                abs(mid_high - prev_mid_close),
                abs(mid_low - prev_mid_close),
            )
        self._tr_values.append(tr)
        if len(self._tr_values) > self.config.atr_period:
            self._tr_values.pop(0)
        self._atr = float(np.mean(self._tr_values))
        return self._atr

    def _in_london_open_session(self, timestamp: pd.Timestamp) -> bool:
        minutes = _minutes_since_midnight(timestamp.time())
        return self._session_start_minute <= minutes < self._session_end_minute

    def _in_impulse_window(self, timestamp: pd.Timestamp) -> bool:
        minutes = _minutes_since_midnight(timestamp.time())
        return self._session_start_minute <= minutes < self._impulse_end_minute

    def _update_impulse_state(self, bar: pd.Series) -> None:
        if self._impulse_count >= self.config.impulse_bars:
            return
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        if self._impulse_open is None:
            self._impulse_open = float(bar["mid_open"])
        self._impulse_close = float(bar["mid_close"])
        self._impulse_high = mid_high if self._impulse_high is None else max(self._impulse_high, mid_high)
        self._impulse_low = mid_low if self._impulse_low is None else min(self._impulse_low, mid_low)
        self._impulse_count += 1

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

        prev_mid_close = self._prev_mid_close
        mid_close = float(bar["mid_close"])
        atr = self._update_atr(bar, prev_mid_close)
        self._prev_mid_close = mid_close

        if not self._in_london_open_session(timestamp):
            return None

        if self._in_impulse_window(timestamp):
            self._update_impulse_state(bar)
            return None

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if prev_mid_close is None or atr <= 0:
            return None
        if (
            self._impulse_count < self.config.impulse_bars
            or self._impulse_open is None
            or self._impulse_close is None
            or self._impulse_high is None
            or self._impulse_low is None
        ):
            return None

        impulse_move = self._impulse_close - self._impulse_open
        impulse_size = abs(impulse_move)
        if impulse_size <= 0:
            return None
        impulse_size_atr = impulse_size / atr
        if impulse_size_atr < self.config.impulse_threshold_atr:
            return None

        impulse_midpoint = (self._impulse_high + self._impulse_low) / 2.0
        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.target_atr_multiple
        symbol = self._extract_symbol(bar)

        # Strong upward impulse, then bearish midpoint cross -> fade short.
        if impulse_move > 0 and prev_mid_close >= impulse_midpoint and mid_close < impulse_midpoint:
            entry_reference = float(bar["bid_close"])
            self._traded_today = True
            return Order(
                symbol=symbol,
                timeframe=self.config.timeframe,
                side="short",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=entry_reference + stop_distance,
                take_profit=entry_reference - target_distance,
                max_holding_bars=self.config.max_holding_bars,
            )

        # Strong downward impulse, then bullish midpoint cross -> fade long.
        if impulse_move < 0 and prev_mid_close <= impulse_midpoint and mid_close > impulse_midpoint:
            entry_reference = float(bar["ask_close"])
            self._traded_today = True
            return Order(
                symbol=symbol,
                timeframe=self.config.timeframe,
                side="long",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=entry_reference - stop_distance,
                take_profit=entry_reference + target_distance,
                max_holding_bars=self.config.max_holding_bars,
            )

        return None
