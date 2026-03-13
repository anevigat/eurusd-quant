from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


def _in_window(timestamp: pd.Timestamp, start: time, end: time) -> bool:
    current = timestamp.time()
    return start <= current < end


@dataclass(frozen=True)
class VWAPSessionOpenConfig:
    timeframe: str
    atr_period: int
    deviation_threshold_atr: float
    london_window_start_utc: str
    london_window_end_utc: str
    new_york_window_start_utc: str
    new_york_window_end_utc: str
    stop_atr_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "VWAPSessionOpenConfig":
        return cls(**data)


class VWAPSessionOpenStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: VWAPSessionOpenConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.deviation_threshold_atr <= 0:
            raise ValueError("deviation_threshold_atr must be > 0")
        if config.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be > 0")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")

        self._london_start = parse_hhmm(config.london_window_start_utc)
        self._london_end = parse_hhmm(config.london_window_end_utc)
        self._ny_start = parse_hhmm(config.new_york_window_start_utc)
        self._ny_end = parse_hhmm(config.new_york_window_end_utc)

        self._current_date: date | None = None
        self._traded_today = False
        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []
        self._vwap_sum = 0.0
        self._vwap_count = 0

    def _reset_day(self, day: date) -> None:
        self._current_date = day
        self._traded_today = False
        self._prev_mid_close = None
        self._tr_values = []
        self._vwap_sum = 0.0
        self._vwap_count = 0

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        normalized = normalize_symbol(str(raw_symbol))
        if not normalized:
            return self.DEFAULT_SYMBOL
        return normalized

    def _in_open_window(self, timestamp: pd.Timestamp) -> bool:
        return _in_window(timestamp, self._london_start, self._london_end) or _in_window(
            timestamp, self._ny_start, self._ny_end
        )

    def _update_atr(self, bar: pd.Series) -> float:
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        mid_close = float(bar["mid_close"])
        if self._prev_mid_close is None:
            tr = mid_high - mid_low
        else:
            tr = max(
                mid_high - mid_low,
                abs(mid_high - self._prev_mid_close),
                abs(mid_low - self._prev_mid_close),
            )
        self._tr_values.append(tr)
        if len(self._tr_values) > self.config.atr_period:
            self._tr_values.pop(0)
        self._prev_mid_close = mid_close
        return float(np.mean(self._tr_values))

    def _update_vwap_proxy(self, bar: pd.Series) -> float:
        typical = (float(bar["mid_high"]) + float(bar["mid_low"]) + float(bar["mid_close"])) / 3.0
        self._vwap_sum += typical
        self._vwap_count += 1
        return self._vwap_sum / self._vwap_count

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        timestamp: pd.Timestamp = bar["timestamp"]
        day = timestamp.date()
        if self._current_date != day:
            self._reset_day(day)

        atr = self._update_atr(bar)
        vwap_proxy = self._update_vwap_proxy(bar)
        mid_close = float(bar["mid_close"])

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if not self._in_open_window(timestamp):
            return None
        if atr <= 0:
            return None

        deviation = mid_close - vwap_proxy
        deviation_atr = abs(deviation) / atr
        if deviation_atr < self.config.deviation_threshold_atr:
            return None

        stop_distance = atr * self.config.stop_atr_multiple
        symbol = self._extract_symbol(bar)

        # Positive deviation: fade short back to VWAP.
        if deviation > 0:
            entry_reference = float(bar["bid_close"])
            take_profit = float(vwap_proxy)
            stop_loss = entry_reference + stop_distance
            if take_profit >= entry_reference:
                return None
            self._traded_today = True
            return Order(
                symbol=symbol,
                timeframe=self.config.timeframe,
                side="short",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=stop_loss,
                take_profit=take_profit,
                max_holding_bars=self.config.max_holding_bars,
            )

        # Negative deviation: fade long back to VWAP.
        if deviation < 0:
            entry_reference = float(bar["ask_close"])
            take_profit = float(vwap_proxy)
            stop_loss = entry_reference - stop_distance
            if take_profit <= entry_reference:
                return None
            self._traded_today = True
            return Order(
                symbol=symbol,
                timeframe=self.config.timeframe,
                side="long",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=stop_loss,
                take_profit=take_profit,
                max_holding_bars=self.config.max_holding_bars,
            )

        return None
