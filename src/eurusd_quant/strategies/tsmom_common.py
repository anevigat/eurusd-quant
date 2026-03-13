from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import pandas as pd

from eurusd_quant.execution.models import Order, Position
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol

Signal = Literal["long", "short"] | None


@dataclass(frozen=True)
class TrendCommonConfig:
    timeframe: str
    atr_period: int
    atr_stop_multiple: float | None
    trailing_stop: bool
    max_holding_bars: int = 252


class TrendMomentumStrategyBase(BaseStrategy):
    SUPPORTED_TIMEFRAMES = {"4h", "1d"}

    def __init__(self, config: TrendCommonConfig) -> None:
        if config.timeframe not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(self.SUPPORTED_TIMEFRAMES)}")
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.atr_stop_multiple is not None and config.atr_stop_multiple <= 0:
            raise ValueError("atr_stop_multiple must be > 0 when provided")
        if config.trailing_stop and config.atr_stop_multiple is None:
            raise ValueError("trailing_stop requires atr_stop_multiple")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")

        self.config = config
        self._symbol = "EURUSD"
        self._timestamps: list[pd.Timestamp] = []
        self._mid_close: list[float] = []
        self._mid_high: list[float] = []
        self._mid_low: list[float] = []
        self._prev_close: float | None = None
        self._atr_values: list[float] = []
        self._current_atr: float | None = None
        self._latest_signal: Signal = None
        self._active_position_key: tuple[pd.Timestamp, str] | None = None
        self._highest_since_entry: float | None = None
        self._lowest_since_entry: float | None = None

    def on_bar(self, bar: pd.Series) -> None:
        close = float(bar["mid_close"])
        high = float(bar["mid_high"])
        low = float(bar["mid_low"])
        if math.isnan(close) or math.isnan(high) or math.isnan(low):
            self._latest_signal = None
            return

        raw_symbol = bar.get("symbol", self._symbol)
        self._symbol = normalize_symbol(str(raw_symbol))

        self._timestamps.append(pd.Timestamp(bar["timestamp"]))
        self._mid_close.append(close)
        self._mid_high.append(high)
        self._mid_low.append(low)

        if self._prev_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._atr_values.append(true_range)
        if len(self._atr_values) > self.config.atr_period:
            self._atr_values.pop(0)
        self._current_atr = sum(self._atr_values) / len(self._atr_values)
        self._prev_close = close
        self._latest_signal = self._compute_signal()

    def should_exit_position(
        self,
        bar: pd.Series,
        position: Position,
    ) -> bool:
        expected_side = "long" if position.side == "long" else "short"
        return self._latest_signal != expected_side

    def update_open_position(
        self,
        bar: pd.Series,
        position: Position,
    ) -> tuple[float, float] | None:
        if not self.config.trailing_stop or self.config.atr_stop_multiple is None or self._current_atr is None:
            return None

        position_key = (position.entry_time, position.side)
        bar_high = float(bar["mid_high"])
        bar_low = float(bar["mid_low"])

        if self._active_position_key != position_key:
            self._active_position_key = position_key
            self._highest_since_entry = max(position.entry_price, bar_high)
            self._lowest_since_entry = min(position.entry_price, bar_low)
        else:
            assert self._highest_since_entry is not None
            assert self._lowest_since_entry is not None
            self._highest_since_entry = max(self._highest_since_entry, bar_high)
            self._lowest_since_entry = min(self._lowest_since_entry, bar_low)

        trailing_distance = self._current_atr * self.config.atr_stop_multiple
        if position.side == "long":
            assert self._highest_since_entry is not None
            stop_loss = max(float(position.stop_loss), self._highest_since_entry - trailing_distance)
            take_profit = float("inf")
        else:
            assert self._lowest_since_entry is not None
            stop_loss = min(float(position.stop_loss), self._lowest_since_entry + trailing_distance)
            take_profit = float("-inf")
        return float(stop_loss), float(take_profit)

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        if has_open_position or has_pending_order or self._latest_signal is None:
            return None
        if not self._is_ready():
            return None

        timestamp = pd.Timestamp(bar["timestamp"])
        side = self._latest_signal
        if side == "long":
            entry_reference = float(bar["ask_close"])
            if self.config.atr_stop_multiple is None or self._current_atr is None:
                stop_loss = float("-inf")
            else:
                stop_loss = entry_reference - (self._current_atr * self.config.atr_stop_multiple)
            take_profit = float("inf")
        else:
            entry_reference = float(bar["bid_close"])
            if self.config.atr_stop_multiple is None or self._current_atr is None:
                stop_loss = float("inf")
            else:
                stop_loss = entry_reference + (self._current_atr * self.config.atr_stop_multiple)
            take_profit = float("-inf")

        return Order(
            symbol=self._symbol,
            timeframe=self.config.timeframe,
            side=side,
            signal_time=timestamp,
            entry_reference=entry_reference,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            max_holding_bars=self.config.max_holding_bars,
        )

    def _is_ready(self) -> bool:
        raise NotImplementedError

    def _compute_signal(self) -> Signal:
        raise NotImplementedError
