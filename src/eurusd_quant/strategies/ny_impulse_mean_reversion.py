from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy


@dataclass(frozen=True)
class NYImpulseMeanReversionConfig:
    timeframe: str
    impulse_start_utc: str
    impulse_end_utc: str
    entry_start_utc: str
    entry_end_utc: str
    impulse_threshold_pips: float
    entry_mode: str
    retracement_target_ratio: float
    stop_buffer_pips: float
    max_holding_bars: int
    one_trade_per_day: bool = True
    allowed_side: str = "both"

    @classmethod
    def from_dict(cls, data: dict) -> "NYImpulseMeanReversionConfig":
        return cls(**data)


class NYImpulseMeanReversionStrategy(BaseStrategy):
    PIP_SIZE = 0.0001

    def __init__(self, config: NYImpulseMeanReversionConfig) -> None:
        self.config = config
        self._impulse_start: time = parse_hhmm(config.impulse_start_utc)
        self._impulse_end: time = parse_hhmm(config.impulse_end_utc)
        self._entry_start: time = parse_hhmm(config.entry_start_utc)
        self._entry_end: time = parse_hhmm(config.entry_end_utc)

        if config.entry_mode != "impulse_midpoint_cross":
            raise ValueError("MVP supports only entry_mode='impulse_midpoint_cross'")
        if config.allowed_side not in {"both", "long_only", "short_only"}:
            raise ValueError("allowed_side must be 'both', 'long_only', or 'short_only'")

        self._current_date: date | None = None
        self._impulse_high: float | None = None
        self._impulse_low: float | None = None
        self._impulse_open: float | None = None
        self._impulse_close: float | None = None
        self._impulse_bars: int = 0
        self._traded_today = False
        self._prev_mid_close: float | None = None

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._impulse_high = None
        self._impulse_low = None
        self._impulse_open = None
        self._impulse_close = None
        self._impulse_bars = 0
        self._traded_today = False
        self._prev_mid_close = None

    def _update_impulse(self, bar: pd.Series, timestamp: pd.Timestamp) -> None:
        if not in_time_window(timestamp, self._impulse_start, self._impulse_end):
            return
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        if self._impulse_open is None:
            self._impulse_open = float(bar["mid_open"])
        self._impulse_close = float(bar["mid_close"])
        self._impulse_high = mid_high if self._impulse_high is None else max(self._impulse_high, mid_high)
        self._impulse_low = mid_low if self._impulse_low is None else min(self._impulse_low, mid_low)
        self._impulse_bars += 1

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
        self._update_impulse(bar, timestamp)
        mid_close = float(bar["mid_close"])
        self._prev_mid_close = mid_close

        if not in_time_window(timestamp, self._entry_start, self._entry_end):
            return None
        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if (
            self._impulse_bars == 0
            or self._impulse_high is None
            or self._impulse_low is None
            or self._impulse_open is None
            or self._impulse_close is None
            or prev_mid_close is None
        ):
            return None

        impulse_size = self._impulse_high - self._impulse_low
        threshold = self.config.impulse_threshold_pips * self.PIP_SIZE
        if impulse_size < threshold:
            return None

        impulse_midpoint = (self._impulse_high + self._impulse_low) / 2.0
        stop_buffer = self.config.stop_buffer_pips * self.PIP_SIZE
        retracement_target = self.config.retracement_target_ratio * impulse_size

        # Bullish impulse -> mean-reversion short on midpoint cross-down.
        if (
            self._impulse_close > self._impulse_open
            and self.config.allowed_side != "long_only"
            and prev_mid_close >= impulse_midpoint
            and mid_close < impulse_midpoint
        ):
            entry_reference = float(bar["bid_close"])
            stop_loss = self._impulse_high + stop_buffer
            take_profit = entry_reference - retracement_target
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

        # Bearish impulse -> mean-reversion long on midpoint cross-up.
        if (
            self._impulse_close < self._impulse_open
            and self.config.allowed_side != "short_only"
            and prev_mid_close <= impulse_midpoint
            and mid_close > impulse_midpoint
        ):
            entry_reference = float(bar["ask_close"])
            stop_loss = self._impulse_low - stop_buffer
            take_profit = entry_reference + retracement_target
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

        return None
