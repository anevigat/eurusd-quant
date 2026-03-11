from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from eurusd_quant.exits.base_exit import ExitModel


@dataclass(frozen=True)
class RetracementExit(ExitModel):
    target_reversion_ratio: float

    def initialize_position(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        context: dict[str, Any],
    ) -> tuple[float, float, dict[str, Any]]:
        impulse_size = float(context.get("impulse_size", 0.0))
        target_distance = max(0.0, self.target_reversion_ratio * impulse_size)
        if target_distance <= 0:
            return stop_loss, take_profit, {}
        if side == "long":
            return stop_loss, entry_price + target_distance, {}
        if side == "short":
            return stop_loss, entry_price - target_distance, {}
        raise ValueError(f"Unsupported side: {side}")

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
        return stop_loss, take_profit, state
