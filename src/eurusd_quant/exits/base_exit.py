from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class ExitModel(ABC):
    @abstractmethod
    def initialize_position(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        context: dict[str, Any],
    ) -> tuple[float, float, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError
