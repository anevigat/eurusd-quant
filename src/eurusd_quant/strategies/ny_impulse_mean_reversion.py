from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any

import pandas as pd

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.exits import ExitModel, build_exit_model
from eurusd_quant.execution.models import Order, Position
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol, pips_to_price


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
    atr_period: int = 14
    exit_model: str = "retracement"
    atr_target_multiple: float = 1.0
    retracement_entry_ratio: float = 0.5
    atr_trail_multiple: float = 0.8
    initial_stop_atr: float = 1.0
    breakeven_trigger_atr: float = 0.5
    trailing_start_atr: float = 1.0
    one_trade_per_day: bool = True
    allowed_side: str = "both"

    @classmethod
    def from_dict(cls, data: dict) -> "NYImpulseMeanReversionConfig":
        return cls(**data)


class NYImpulseMeanReversionStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

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
        if config.retracement_entry_ratio <= 0 or config.retracement_entry_ratio >= 1:
            raise ValueError("retracement_entry_ratio must be between 0 and 1 (exclusive)")
        if config.exit_model not in {
            "retracement",
            "atr",
            "atr_trailing",
            "breakeven_atr_trailing",
        }:
            raise ValueError(
                "exit_model must be 'retracement', 'atr', 'atr_trailing', or 'breakeven_atr_trailing'"
            )
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.atr_target_multiple <= 0:
            raise ValueError("atr_target_multiple must be > 0")
        if config.atr_trail_multiple <= 0:
            raise ValueError("atr_trail_multiple must be > 0")
        if config.initial_stop_atr <= 0:
            raise ValueError("initial_stop_atr must be > 0")
        if config.breakeven_trigger_atr <= 0:
            raise ValueError("breakeven_trigger_atr must be > 0")
        if config.trailing_start_atr <= 0:
            raise ValueError("trailing_start_atr must be > 0")

        self._current_date: date | None = None
        self._impulse_high: float | None = None
        self._impulse_low: float | None = None
        self._impulse_open: float | None = None
        self._impulse_close: float | None = None
        self._impulse_bars: int = 0
        self._traded_today = False
        self._prev_mid_close: float | None = None
        self._atr_values: list[float] = []
        self._atr: float | None = None
        self._exit_model: ExitModel = self._build_exit_model(config)
        self._pending_exit_context: dict[str, Any] | None = None
        self._pending_exit_state: dict[str, Any] | None = None
        self._active_exit_context: dict[str, Any] | None = None
        self._active_exit_state: dict[str, Any] | None = None

    def _build_exit_model(self, config: NYImpulseMeanReversionConfig) -> ExitModel:
        if config.exit_model == "retracement":
            return build_exit_model(
                "retracement",
                {"target_reversion_ratio": config.retracement_target_ratio},
            )
        if config.exit_model == "atr":
            return build_exit_model(
                "atr",
                {"atr_target_multiple": config.atr_target_multiple},
            )
        if config.exit_model == "atr_trailing":
            return build_exit_model(
                "atr_trailing",
                {
                    "atr_trail_multiple": config.atr_trail_multiple,
                    "initial_stop_atr": config.initial_stop_atr,
                },
            )
        return build_exit_model(
            "breakeven_atr_trailing",
            {
                "initial_stop_atr": config.initial_stop_atr,
                "breakeven_trigger_atr": config.breakeven_trigger_atr,
                "trailing_start_atr": config.trailing_start_atr,
                "atr_trail_multiple": config.atr_trail_multiple,
            },
        )

    def _clear_active_exit_state(self) -> None:
        self._active_exit_context = None
        self._active_exit_state = None

    def _reset_day(self, current_day: date) -> None:
        self._current_date = current_day
        self._impulse_high = None
        self._impulse_low = None
        self._impulse_open = None
        self._impulse_close = None
        self._impulse_bars = 0
        self._traded_today = False
        self._prev_mid_close = None
        self._atr_values = []
        self._atr = None

    def update_open_position(
        self,
        bar: pd.Series,
        position: Position,
    ) -> tuple[float, float] | None:
        if self._active_exit_context is None:
            if self._pending_exit_context is None:
                return None
            self._active_exit_context = dict(self._pending_exit_context)
            self._active_exit_state = dict(self._pending_exit_state or {})
            self._pending_exit_context = None
            self._pending_exit_state = None

        if self._active_exit_context is None:
            return None

        context = dict(self._active_exit_context)
        if self._atr is not None:
            context["atr"] = self._atr
        state = dict(self._active_exit_state or {})

        stop_loss, take_profit, new_state = self._exit_model.update(
            side=position.side,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            bar=bar,
            context=context,
            state=state,
        )
        self._active_exit_state = new_state
        return float(stop_loss), float(take_profit)

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

    def _update_atr(self, bar: pd.Series, prev_mid_close: float | None) -> None:
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
        self._atr_values.append(tr)
        if len(self._atr_values) > self.config.atr_period:
            self._atr_values.pop(0)
        self._atr = sum(self._atr_values) / len(self._atr_values)

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        timestamp: pd.Timestamp = bar["timestamp"]
        symbol = self._extract_symbol(bar)
        bar_day = timestamp.date()
        if self._current_date != bar_day:
            self._reset_day(bar_day)
        if not has_open_position:
            self._clear_active_exit_state()

        prev_mid_close = self._prev_mid_close
        self._update_impulse(bar, timestamp)
        self._update_atr(bar, prev_mid_close)
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
        threshold = pips_to_price(symbol, self.config.impulse_threshold_pips)
        if impulse_size < threshold:
            return None

        retracement_level_short = self._impulse_high - (
            self.config.retracement_entry_ratio * impulse_size
        )
        retracement_level_long = self._impulse_low + (
            self.config.retracement_entry_ratio * impulse_size
        )
        stop_buffer = pips_to_price(symbol, self.config.stop_buffer_pips)
        retracement_target = self.config.retracement_target_ratio * impulse_size
        atr_target = (self._atr or 0.0) * self.config.atr_target_multiple

        # Bullish impulse -> mean-reversion short on retracement-level cross-down.
        if (
            self._impulse_close > self._impulse_open
            and self.config.allowed_side != "long_only"
            and prev_mid_close >= retracement_level_short
            and mid_close < retracement_level_short
        ):
            entry_reference = float(bar["bid_close"])
            stop_loss = self._impulse_high + stop_buffer
            if self.config.exit_model == "retracement":
                take_profit = entry_reference - retracement_target
            else:
                take_profit = entry_reference - atr_target
            exit_context = {"impulse_size": impulse_size, "atr": self._atr or 0.0}
            stop_loss, take_profit, exit_state = self._exit_model.initialize_position(
                side="short",
                entry_price=entry_reference,
                stop_loss=stop_loss,
                take_profit=take_profit,
                context=exit_context,
            )
            if stop_loss > entry_reference and take_profit < entry_reference:
                self._pending_exit_context = exit_context
                self._pending_exit_state = exit_state
                self._traded_today = True
                return Order(
                    symbol=symbol,
                    timeframe="15m",
                    side="short",
                    signal_time=timestamp,
                    entry_reference=entry_reference,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    max_holding_bars=self.config.max_holding_bars,
                )

        # Bearish impulse -> mean-reversion long on retracement-level cross-up.
        if (
            self._impulse_close < self._impulse_open
            and self.config.allowed_side != "short_only"
            and prev_mid_close <= retracement_level_long
            and mid_close > retracement_level_long
        ):
            entry_reference = float(bar["ask_close"])
            stop_loss = self._impulse_low - stop_buffer
            if self.config.exit_model == "retracement":
                take_profit = entry_reference + retracement_target
            else:
                take_profit = entry_reference + atr_target
            exit_context = {"impulse_size": impulse_size, "atr": self._atr or 0.0}
            stop_loss, take_profit, exit_state = self._exit_model.initialize_position(
                side="long",
                entry_price=entry_reference,
                stop_loss=stop_loss,
                take_profit=take_profit,
                context=exit_context,
            )
            if stop_loss < entry_reference and take_profit > entry_reference:
                self._pending_exit_context = exit_context
                self._pending_exit_state = exit_state
                self._traded_today = True
                return Order(
                    symbol=symbol,
                    timeframe="15m",
                    side="long",
                    signal_time=timestamp,
                    entry_reference=entry_reference,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    max_holding_bars=self.config.max_holding_bars,
                )

        return None

    def _extract_symbol(self, bar: pd.Series) -> str:
        raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        normalized = normalize_symbol(str(raw_symbol))
        if not normalized:
            return self.DEFAULT_SYMBOL
        return normalized
