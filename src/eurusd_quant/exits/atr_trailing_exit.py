from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from eurusd_quant.exits.base_exit import ExitModel


@dataclass(frozen=True)
class ATRTrailingExit(ExitModel):
    atr_trail_multiple: float
    initial_stop_atr: float = 1.0
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
            return stop_loss, take_profit, {"best_price": entry_price}

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
        return init_stop, init_tp, {"best_price": entry_price}

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

        best_price = float(state.get("best_price", entry_price))
        if side == "long":
            best_price = max(best_price, float(bar["bid_high"]))
            trailed_stop = best_price - (self.atr_trail_multiple * atr)
            stop_loss = max(stop_loss, trailed_stop)
        elif side == "short":
            best_price = min(best_price, float(bar["ask_low"]))
            trailed_stop = best_price + (self.atr_trail_multiple * atr)
            stop_loss = min(stop_loss, trailed_stop)
        else:
            raise ValueError(f"Unsupported side: {side}")

        state = dict(state)
        state["best_price"] = best_price
        return stop_loss, take_profit, state
