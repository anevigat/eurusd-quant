from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from eurusd_quant.exits.base_exit import ExitModel


@dataclass(frozen=True)
class BreakevenATRTrailingExit(ExitModel):
    initial_stop_atr: float
    breakeven_trigger_atr: float
    trailing_start_atr: float
    atr_trail_multiple: float
    hard_target_atr: float = 5.0

    def initialize_position(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        context: dict[str, Any],
    ) -> tuple[float, float, dict[str, Any]]:
        atr = float(context.get("atr", 0.0))
        if atr <= 0:
            return stop_loss, take_profit, {"best_price": entry_price, "breakeven_set": False}

        stop_distance = atr * self.initial_stop_atr
        target_distance = atr * self.hard_target_atr
        if side == "long":
            init_stop = entry_price - stop_distance
            init_tp = entry_price + target_distance
        elif side == "short":
            init_stop = entry_price + stop_distance
            init_tp = entry_price - target_distance
        else:
            raise ValueError(f"Unsupported side: {side}")

        return init_stop, init_tp, {"best_price": entry_price, "breakeven_set": False}

    def update(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        bar: pd.Series,
        context: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[float, float, dict[str, Any]]:
        atr = float(context.get("atr", 0.0))
        if atr <= 0:
            return stop_loss, take_profit, state

        state = dict(state)
        best_price = float(state.get("best_price", entry_price))
        breakeven_set = bool(state.get("breakeven_set", False))

        if side == "long":
            best_price = max(best_price, float(bar["bid_high"]))
            profit_atr = (best_price - entry_price) / atr
            if not breakeven_set and profit_atr >= self.breakeven_trigger_atr:
                stop_loss = max(stop_loss, entry_price)
                breakeven_set = True
            if profit_atr >= self.trailing_start_atr:
                trailed_stop = best_price - (self.atr_trail_multiple * atr)
                stop_loss = max(stop_loss, trailed_stop)
        elif side == "short":
            best_price = min(best_price, float(bar["ask_low"]))
            profit_atr = (entry_price - best_price) / atr
            if not breakeven_set and profit_atr >= self.breakeven_trigger_atr:
                stop_loss = min(stop_loss, entry_price)
                breakeven_set = True
            if profit_atr >= self.trailing_start_atr:
                trailed_stop = best_price + (self.atr_trail_multiple * atr)
                stop_loss = min(stop_loss, trailed_stop)
        else:
            raise ValueError(f"Unsupported side: {side}")

        state["best_price"] = best_price
        state["breakeven_set"] = breakeven_set
        return stop_loss, take_profit, state
