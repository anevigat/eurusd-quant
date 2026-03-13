from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


@dataclass(frozen=True)
class ATRSpikeNewHighLowConfig:
    timeframe: str
    atr_period: int
    atr_median_lookback_bars: int
    atr_spike_threshold: float
    breakout_lookback_bars: int
    stop_atr_multiple: float
    target_atr_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "ATRSpikeNewHighLowConfig":
        return cls(**data)


class ATRSpikeNewHighLowStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: ATRSpikeNewHighLowConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.atr_median_lookback_bars < 2:
            raise ValueError("atr_median_lookback_bars must be >= 2")
        if config.atr_spike_threshold <= 0:
            raise ValueError("atr_spike_threshold must be > 0")
        if config.breakout_lookback_bars < 2:
            raise ValueError("breakout_lookback_bars must be >= 2")
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
        self._high_buffer: list[float] = []
        self._low_buffer: list[float] = []

    def _reset_day(self, day: date) -> None:
        self._current_date = day
        self._traded_today = False

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        symbol = normalize_symbol(str(raw_symbol))
        if not symbol:
            return self.DEFAULT_SYMBOL
        return symbol

    def _update_indicators(self, bar: pd.Series) -> tuple[float, float]:
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
        self._prev_mid_close = mid_close

        self._tr_values.append(tr)
        if len(self._tr_values) > self.config.atr_period:
            self._tr_values.pop(0)
        atr = float(np.mean(self._tr_values))
        if len(self._tr_values) >= self.config.atr_period:
            self._atr_values.append(atr)
            if len(self._atr_values) > self.config.atr_median_lookback_bars:
                self._atr_values.pop(0)

        if len(self._atr_values) < self.config.atr_median_lookback_bars:
            return atr, np.nan
        median_atr = float(np.median(self._atr_values))
        if median_atr <= 0:
            return atr, np.nan
        return atr, float(atr / median_atr)

    def _update_breakout_buffers(self, bar: pd.Series) -> None:
        self._high_buffer.append(float(bar["mid_high"]))
        self._low_buffer.append(float(bar["mid_low"]))
        if len(self._high_buffer) > self.config.breakout_lookback_bars:
            self._high_buffer.pop(0)
            self._low_buffer.pop(0)

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

        prior_highs = self._high_buffer.copy()
        prior_lows = self._low_buffer.copy()
        atr, atr_ratio = self._update_indicators(bar)
        self._update_breakout_buffers(bar)

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if atr <= 0 or not np.isfinite(atr_ratio):
            return None
        if atr_ratio < self.config.atr_spike_threshold:
            return None
        if len(prior_highs) < self.config.breakout_lookback_bars:
            return None

        breakout_high = float(max(prior_highs))
        breakout_low = float(min(prior_lows))
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.target_atr_multiple
        symbol = self._extract_symbol(bar)

        breakout_up = mid_high > breakout_high
        breakout_down = mid_low < breakout_low

        if breakout_up and not breakout_down:
            entry_reference = float(bar["ask_close"])
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

        if breakout_down and not breakout_up:
            entry_reference = float(bar["bid_close"])
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
