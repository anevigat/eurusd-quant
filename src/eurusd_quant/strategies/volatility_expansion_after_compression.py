from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


@dataclass(frozen=True)
class VolatilityExpansionAfterCompressionConfig:
    timeframe: str
    atr_period: int
    compression_threshold: float
    compression_lookback_bars: int
    stop_atr_multiple: float
    target_atr_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "VolatilityExpansionAfterCompressionConfig":
        return cls(**data)


class VolatilityExpansionAfterCompressionStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: VolatilityExpansionAfterCompressionConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.compression_threshold <= 0:
            raise ValueError("compression_threshold must be > 0")
        if config.compression_lookback_bars < 2:
            raise ValueError("compression_lookback_bars must be >= 2")
        if config.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be > 0")
        if config.target_atr_multiple <= 0:
            raise ValueError("target_atr_multiple must be > 0")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")

        self._current_date: date | None = None
        self._traded_today = False

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []
        self._atr_values: list[float] = []

        self._recent_highs: list[float] = []
        self._recent_lows: list[float] = []
        self._armed_breakout_high: float | None = None
        self._armed_breakout_low: float | None = None

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._traded_today = False

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        symbol = normalize_symbol(str(raw_symbol))
        if not symbol:
            return self.DEFAULT_SYMBOL
        return symbol

    def _update_atr(self, bar: pd.Series) -> float:
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        mid_close = float(bar["mid_close"])

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
        if len(self._tr_values) > self.config.atr_period:
            self._tr_values.pop(0)
        self._prev_mid_close = mid_close

        if len(self._tr_values) < self.config.atr_period:
            return np.nan
        atr = float(np.mean(self._tr_values))
        self._atr_values.append(atr)
        if len(self._atr_values) > self.config.compression_lookback_bars:
            self._atr_values.pop(0)
        return atr

    def _update_breakout_window(self, bar: pd.Series) -> None:
        self._recent_highs.append(float(bar["mid_high"]))
        self._recent_lows.append(float(bar["mid_low"]))
        if len(self._recent_highs) > self.config.compression_lookback_bars:
            self._recent_highs.pop(0)
            self._recent_lows.pop(0)

    def _update_compression_state(self, atr: float) -> None:
        if np.isnan(atr):
            return
        if len(self._atr_values) < self.config.compression_lookback_bars:
            return
        if len(self._recent_highs) < self.config.compression_lookback_bars:
            return

        rolling_median_atr = float(np.median(self._atr_values))
        if rolling_median_atr <= 0:
            return
        if atr <= self.config.compression_threshold * rolling_median_atr:
            self._armed_breakout_high = float(max(self._recent_highs))
            self._armed_breakout_low = float(min(self._recent_lows))

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
        self._update_breakout_window(bar)
        self._update_compression_state(atr)

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if self._armed_breakout_high is None or self._armed_breakout_low is None:
            return None
        if np.isnan(atr) or atr <= 0:
            return None

        mid_close = float(bar["mid_close"])
        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])
        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.target_atr_multiple
        symbol = self._extract_symbol(bar)

        if mid_close > self._armed_breakout_high:
            entry_reference = ask_close
            self._armed_breakout_high = None
            self._armed_breakout_low = None
            if self.config.one_trade_per_day:
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

        if mid_close < self._armed_breakout_low:
            entry_reference = bid_close
            self._armed_breakout_high = None
            self._armed_breakout_low = None
            if self.config.one_trade_per_day:
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

        return None
