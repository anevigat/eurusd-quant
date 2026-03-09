from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy


@dataclass(frozen=True)
class FalseBreakoutReversalConfig:
    timeframe: str
    asian_range_start_utc: str
    asian_range_end_utc: str
    entry_start_utc: str
    entry_end_utc: str
    break_buffer_pips: float
    reentry_buffer_pips: float
    atr_period: int
    atr_min_threshold: float
    stop_mode: str
    stop_atr_buffer_multiple: float
    exit_model: str
    take_profit_r: float
    max_holding_bars: int
    atr_target_multiple: float = 1.2
    allowed_side: str = "both"
    one_trade_per_day: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "FalseBreakoutReversalConfig":
        data = dict(data)
        # Backward compatibility for older configs.
        if "exit_model" not in data and "take_profit_mode" in data:
            data["exit_model"] = data.pop("take_profit_mode")
        return cls(**data)


class FalseBreakoutReversalStrategy(BaseStrategy):
    PIP_SIZE = 0.0001

    def __init__(self, config: FalseBreakoutReversalConfig) -> None:
        self.config = config
        self._asian_start: time = parse_hhmm(config.asian_range_start_utc)
        self._asian_end: time = parse_hhmm(config.asian_range_end_utc)
        self._entry_start: time = parse_hhmm(config.entry_start_utc)
        self._entry_end: time = parse_hhmm(config.entry_end_utc)

        if config.stop_mode != "outside_break_extreme":
            raise ValueError("MVP supports only stop_mode='outside_break_extreme'")
        if config.exit_model not in {"range_midpoint", "fixed_r", "atr_target"}:
            raise ValueError("exit_model must be 'range_midpoint', 'fixed_r', or 'atr_target'")
        if config.allowed_side not in {"both", "long_only", "short_only"}:
            raise ValueError("allowed_side must be 'both', 'long_only', or 'short_only'")

        self._current_date: date | None = None
        self._asian_high: float | None = None
        self._asian_low: float | None = None
        self._asian_bars: int = 0
        self._traded_today = False

        self._false_break_below_seen = False
        self._false_break_above_seen = False
        self._break_below_extreme: float | None = None
        self._break_above_extreme: float | None = None
        self._break_below_seen_at: pd.Timestamp | None = None
        self._break_above_seen_at: pd.Timestamp | None = None

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

        self._false_break_below_seen = False
        self._false_break_above_seen = False
        self._break_below_extreme = None
        self._break_above_extreme = None
        self._break_below_seen_at = None
        self._break_above_seen_at = None

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

    def _update_false_break_state(self, bar: pd.Series, timestamp: pd.Timestamp) -> None:
        if self._asian_high is None or self._asian_low is None or self._asian_bars == 0:
            return
        if in_time_window(timestamp, self._asian_start, self._asian_end):
            return
        break_buffer = self.config.break_buffer_pips * self.PIP_SIZE
        bid_low = float(bar["bid_low"])
        ask_high = float(bar["ask_high"])

        if bid_low < (self._asian_low - break_buffer):
            if not self._false_break_below_seen:
                self._break_below_seen_at = timestamp
            self._false_break_below_seen = True
            self._break_below_extreme = (
                bid_low
                if self._break_below_extreme is None
                else min(self._break_below_extreme, bid_low)
            )

        if ask_high > (self._asian_high + break_buffer):
            if not self._false_break_above_seen:
                self._break_above_seen_at = timestamp
            self._false_break_above_seen = True
            self._break_above_extreme = (
                ask_high
                if self._break_above_extreme is None
                else max(self._break_above_extreme, ask_high)
            )

    def _fixed_r_take_profit(self, side: str, entry_reference: float, stop_loss: float) -> float:
        risk = abs(entry_reference - stop_loss)
        if side == "long":
            return entry_reference + (risk * self.config.take_profit_r)
        return entry_reference - (risk * self.config.take_profit_r)

    def _take_profit(
        self,
        side: str,
        entry_reference: float,
        stop_loss: float,
        atr: float,
    ) -> float:
        if self.config.exit_model == "fixed_r":
            return self._fixed_r_take_profit(side, entry_reference, stop_loss)

        if self.config.exit_model == "atr_target":
            if side == "long":
                return entry_reference + (atr * self.config.atr_target_multiple)
            return entry_reference - (atr * self.config.atr_target_multiple)

        fixed_r_tp = self._fixed_r_take_profit(side, entry_reference, stop_loss)
        if self._asian_high is None or self._asian_low is None:
            return fixed_r_tp

        midpoint = (self._asian_high + self._asian_low) / 2.0
        if side == "long" and midpoint > entry_reference:
            return midpoint
        if side == "short" and midpoint < entry_reference:
            return midpoint
        return fixed_r_tp

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
        self._update_false_break_state(bar, timestamp)

        if not in_time_window(timestamp, self._entry_start, self._entry_end):
            return None
        if self._asian_bars == 0 or self._asian_high is None or self._asian_low is None:
            return None
        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None

        atr = self._current_atr()
        if np.isnan(atr) or atr < self.config.atr_min_threshold:
            return None

        reentry_buffer = self.config.reentry_buffer_pips * self.PIP_SIZE
        atr_buffer = atr * self.config.stop_atr_buffer_multiple
        bid_close = float(bar["bid_close"])
        ask_close = float(bar["ask_close"])

        if (
            self.config.allowed_side != "short_only"
            and self._false_break_below_seen
            and self._break_below_extreme is not None
            and self._break_below_seen_at is not None
            and timestamp > self._break_below_seen_at
        ):
            if bid_close >= (self._asian_low + reentry_buffer):
                entry_reference = ask_close
                stop_loss = self._break_below_extreme - atr_buffer
                if stop_loss < entry_reference:
                    take_profit = self._take_profit("long", entry_reference, stop_loss, atr)
                    if take_profit > entry_reference:
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

        if (
            self.config.allowed_side != "long_only"
            and self._false_break_above_seen
            and self._break_above_extreme is not None
            and self._break_above_seen_at is not None
            and timestamp > self._break_above_seen_at
        ):
            if ask_close <= (self._asian_high - reentry_buffer):
                entry_reference = bid_close
                stop_loss = self._break_above_extreme + atr_buffer
                if stop_loss > entry_reference:
                    take_profit = self._take_profit("short", entry_reference, stop_loss, atr)
                    if take_profit < entry_reference:
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

        return None
