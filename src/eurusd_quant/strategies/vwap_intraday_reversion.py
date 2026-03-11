from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


@dataclass(frozen=True)
class VWAPIntradayReversionConfig:
    timeframe: str
    session_start_utc: str
    session_end_utc: str
    atr_period: int
    deviation_threshold_atr: float
    stop_atr_multiple: float
    target_reversion_ratio: float
    max_holding_bars: int
    one_trade_per_day: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "VWAPIntradayReversionConfig":
        return cls(**data)


class VWAPIntradayReversionStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: VWAPIntradayReversionConfig) -> None:
        self.config = config
        self._session_start: time = parse_hhmm(config.session_start_utc)
        self._session_end: time = parse_hhmm(config.session_end_utc)

        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.deviation_threshold_atr <= 0:
            raise ValueError("deviation_threshold_atr must be > 0")
        if config.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be > 0")
        if config.target_reversion_ratio <= 0:
            raise ValueError("target_reversion_ratio must be > 0")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")

        self._current_date: date | None = None
        self._traded_today = False

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []

        self._cum_typical_sum = 0.0
        self._cum_typical_count = 0

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._traded_today = False
        self._cum_typical_sum = 0.0
        self._cum_typical_count = 0

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        normalized = normalize_symbol(str(raw_symbol))
        if not normalized:
            return self.DEFAULT_SYMBOL
        return normalized

    def _update_atr(self, mid_high: float, mid_low: float, mid_close: float) -> None:
        high_low = mid_high - mid_low
        if self._prev_mid_close is None:
            tr = high_low
        else:
            tr = max(
                high_low,
                abs(mid_high - self._prev_mid_close),
                abs(mid_low - self._prev_mid_close),
            )
        self._tr_values.append(tr)
        self._prev_mid_close = mid_close

    def _current_atr(self) -> float:
        if len(self._tr_values) < self.config.atr_period:
            return np.nan
        return float(np.mean(self._tr_values[-self.config.atr_period :]))

    def _update_vwap_proxy(self, mid_high: float, mid_low: float, mid_close: float) -> float:
        typical_price = (mid_high + mid_low + mid_close) / 3.0
        self._cum_typical_sum += typical_price
        self._cum_typical_count += 1
        return self._cum_typical_sum / self._cum_typical_count

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        timestamp: pd.Timestamp = bar["timestamp"]
        current_day = timestamp.date()
        if self._current_date != current_day:
            self._reset_day(current_day)

        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        mid_close = float(bar["mid_close"])
        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])

        self._update_atr(mid_high=mid_high, mid_low=mid_low, mid_close=mid_close)
        vwap_proxy = self._update_vwap_proxy(mid_high=mid_high, mid_low=mid_low, mid_close=mid_close)

        if not in_time_window(timestamp, self._session_start, self._session_end):
            return None
        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None

        atr = self._current_atr()
        if np.isnan(atr) or atr <= 0:
            return None

        deviation = mid_close - vwap_proxy
        deviation_atr = deviation / atr
        threshold = self.config.deviation_threshold_atr
        stop_distance = atr * self.config.stop_atr_multiple
        symbol = self._extract_symbol(bar)

        if deviation_atr >= threshold:
            entry_reference = bid_close
            target_distance = abs(entry_reference - vwap_proxy) * self.config.target_reversion_ratio
            if target_distance <= 0:
                return None
            stop_loss = entry_reference + stop_distance
            take_profit = entry_reference - target_distance
            if stop_loss > entry_reference and take_profit < entry_reference:
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

        if deviation_atr <= -threshold:
            entry_reference = ask_close
            target_distance = abs(entry_reference - vwap_proxy) * self.config.target_reversion_ratio
            if target_distance <= 0:
                return None
            stop_loss = entry_reference - stop_distance
            take_profit = entry_reference + target_distance
            if stop_loss < entry_reference and take_profit > entry_reference:
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
