from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from eurusd_quant.execution.models import Order
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol


@dataclass(frozen=True)
class HeadShouldersReversalConfig:
    timeframe: str
    atr_period: int
    shoulder_tolerance_atr: float
    head_min_excess_atr: float
    stop_atr_multiple: float
    target_atr_multiple: float
    max_holding_bars: int
    pattern_lookback_bars: int = 40
    one_trade_per_day: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "HeadShouldersReversalConfig":
        return cls(**data)


class HeadShouldersReversalStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: HeadShouldersReversalConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.shoulder_tolerance_atr <= 0:
            raise ValueError("shoulder_tolerance_atr must be > 0")
        if config.head_min_excess_atr <= 0:
            raise ValueError("head_min_excess_atr must be > 0")
        if config.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be > 0")
        if config.target_atr_multiple <= 0:
            raise ValueError("target_atr_multiple must be > 0")
        if config.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be >= 1")
        if config.pattern_lookback_bars < 12:
            raise ValueError("pattern_lookback_bars must be >= 12")

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

    def _update_bars(self, bar: pd.Series) -> None:
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
        if len(self._bars) > self.config.pattern_lookback_bars:
            self._bars.pop(0)

    def _swing_highs(self) -> list[int]:
        out: list[int] = []
        for i in range(1, len(self._bars) - 1):
            if self._bars[i]["mid_high"] > self._bars[i - 1]["mid_high"] and self._bars[i]["mid_high"] >= self._bars[i + 1]["mid_high"]:
                out.append(i)
        return out

    def _swing_lows(self) -> list[int]:
        out: list[int] = []
        for i in range(1, len(self._bars) - 1):
            if self._bars[i]["mid_low"] < self._bars[i - 1]["mid_low"] and self._bars[i]["mid_low"] <= self._bars[i + 1]["mid_low"]:
                out.append(i)
        return out

    def _find_bearish_break(self, atr: float) -> bool:
        if len(self._bars) < 10:
            return False
        current_idx = len(self._bars) - 1
        prev_idx = current_idx - 1
        current_close = float(self._bars[current_idx]["mid_close"])
        prev_close = float(self._bars[prev_idx]["mid_close"])

        highs = self._swing_highs()
        for i in range(len(highs) - 2, -1, -1):
            ls_idx = highs[i]
            for j in range(len(highs) - 1, i, -1):
                head_idx = highs[j]
                if head_idx - ls_idx < 2:
                    continue
                for k in range(len(highs) - 1, j, -1):
                    rs_idx = highs[k]
                    if rs_idx > prev_idx:
                        continue
                    if rs_idx - head_idx < 2:
                        continue
                    ls = float(self._bars[ls_idx]["mid_high"])
                    head = float(self._bars[head_idx]["mid_high"])
                    rs = float(self._bars[rs_idx]["mid_high"])
                    if head <= max(ls, rs):
                        continue
                    if (head - max(ls, rs)) < self.config.head_min_excess_atr * atr:
                        continue
                    if abs(ls - rs) > self.config.shoulder_tolerance_atr * atr:
                        continue

                    left_lows = [float(self._bars[x]["mid_low"]) for x in range(ls_idx + 1, head_idx)]
                    right_lows = [float(self._bars[x]["mid_low"]) for x in range(head_idx + 1, rs_idx)]
                    if not left_lows or not right_lows:
                        continue
                    neckline = (min(left_lows) + min(right_lows)) / 2.0
                    if prev_close >= neckline and current_close < neckline:
                        return True
        return False

    def _find_bullish_break(self, atr: float) -> bool:
        if len(self._bars) < 10:
            return False
        current_idx = len(self._bars) - 1
        prev_idx = current_idx - 1
        current_close = float(self._bars[current_idx]["mid_close"])
        prev_close = float(self._bars[prev_idx]["mid_close"])

        lows = self._swing_lows()
        for i in range(len(lows) - 2, -1, -1):
            ls_idx = lows[i]
            for j in range(len(lows) - 1, i, -1):
                head_idx = lows[j]
                if head_idx - ls_idx < 2:
                    continue
                for k in range(len(lows) - 1, j, -1):
                    rs_idx = lows[k]
                    if rs_idx > prev_idx:
                        continue
                    if rs_idx - head_idx < 2:
                        continue
                    ls = float(self._bars[ls_idx]["mid_low"])
                    head = float(self._bars[head_idx]["mid_low"])
                    rs = float(self._bars[rs_idx]["mid_low"])
                    if head >= min(ls, rs):
                        continue
                    if (min(ls, rs) - head) < self.config.head_min_excess_atr * atr:
                        continue
                    if abs(ls - rs) > self.config.shoulder_tolerance_atr * atr:
                        continue

                    left_highs = [float(self._bars[x]["mid_high"]) for x in range(ls_idx + 1, head_idx)]
                    right_highs = [float(self._bars[x]["mid_high"]) for x in range(head_idx + 1, rs_idx)]
                    if not left_highs or not right_highs:
                        continue
                    neckline = (max(left_highs) + max(right_highs)) / 2.0
                    if prev_close <= neckline and current_close > neckline:
                        return True
        return False

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
        self._update_bars(bar)

        if has_open_position or has_pending_order:
            return None
        if self.config.one_trade_per_day and self._traded_today:
            return None
        if np.isnan(atr) or atr <= 0:
            return None
        if len(self._bars) < 10:
            return None

        stop_distance = atr * self.config.stop_atr_multiple
        target_distance = atr * self.config.target_atr_multiple
        symbol = self._extract_symbol(bar)
        current = self._bars[-1]

        if self._find_bearish_break(atr):
            entry_reference = float(current["bid_close"])
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

        if self._find_bullish_break(atr):
            entry_reference = float(current["ask_close"])
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
