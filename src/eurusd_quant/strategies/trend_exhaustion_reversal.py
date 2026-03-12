from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


@dataclass(frozen=True)
class TrendExhaustionReversalConfig:
    timeframe: str
    atr_period: int
    impulse_lookback_bars: int
    impulse_threshold_atr: float
    stop_atr_multiple: float
    target_atr_multiple: float
    max_holding_bars: int
    one_trade_per_day: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "TrendExhaustionReversalConfig":
        return cls(**data)


class TrendExhaustionReversalStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: TrendExhaustionReversalConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.impulse_lookback_bars < 2:
            raise ValueError("impulse_lookback_bars must be >= 2")
        if config.impulse_threshold_atr <= 0:
            raise ValueError("impulse_threshold_atr must be > 0")
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
        self._bars: list[dict[str, float | pd.Timestamp]] = []

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
        self._prev_mid_close = mid_close
        if len(self._tr_values) < self.config.atr_period:
            return np.nan
        return float(np.mean(self._tr_values[-self.config.atr_period :]))

    def _update_bar_buffer(self, bar: pd.Series) -> None:
        self._bars.append(
            {
                "timestamp": bar["timestamp"],
                "mid_open": float(bar["mid_open"]),
                "mid_high": float(bar["mid_high"]),
                "mid_low": float(bar["mid_low"]),
                "mid_close": float(bar["mid_close"]),
                "bid_close": float(bar["bid_close"]),
                "ask_close": float(bar["ask_close"]),
            }
        )
        keep = self.config.impulse_lookback_bars + 1
        if len(self._bars) > keep:
            self._bars.pop(0)

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
        self._update_bar_buffer(bar)

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if np.isnan(atr) or atr <= 0:
            return None

        required = self.config.impulse_lookback_bars + 1
        if len(self._bars) < required:
            return None

        impulse_window = self._bars[-required:-1]
        current_bar = self._bars[-1]
        prior_bar = self._bars[-2]
        impulse_open = float(impulse_window[0]["mid_open"])
        impulse_close = float(impulse_window[-1]["mid_close"])
        impulse_move = impulse_close - impulse_open
        if abs(impulse_move) < self.config.impulse_threshold_atr * atr:
            return None

        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.target_atr_multiple
        symbol = self._extract_symbol(bar)

        if impulse_move > 0 and float(current_bar["mid_close"]) < float(prior_bar["mid_low"]):
            entry_reference = float(current_bar["bid_close"])
            stop_loss = entry_reference + stop_distance
            take_profit = entry_reference - target_distance
            if stop_loss > entry_reference and take_profit < entry_reference:
                if self.config.one_trade_per_day:
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

        if impulse_move < 0 and float(current_bar["mid_close"]) > float(prior_bar["mid_high"]):
            entry_reference = float(current_bar["ask_close"])
            stop_loss = entry_reference - stop_distance
            take_profit = entry_reference + target_distance
            if stop_loss < entry_reference and take_profit > entry_reference:
                if self.config.one_trade_per_day:
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
