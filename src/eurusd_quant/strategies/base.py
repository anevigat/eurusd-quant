from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from eurusd_quant.execution.models import Order


class BaseStrategy(ABC):
    @abstractmethod
    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Optional[Order]:
        raise NotImplementedError
