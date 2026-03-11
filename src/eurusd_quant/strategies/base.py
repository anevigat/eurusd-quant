from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from eurusd_quant.execution.models import Order, Position


class BaseStrategy(ABC):
    def update_open_position(
        self,
        bar: pd.Series,
        position: Position,
    ) -> tuple[float, float] | None:
        return None

    @abstractmethod
    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Optional[Order]:
        raise NotImplementedError
