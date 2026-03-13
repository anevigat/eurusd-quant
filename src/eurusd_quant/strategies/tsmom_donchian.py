from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from eurusd_quant.execution.models import Position
from eurusd_quant.strategies.tsmom_common import Signal, TrendCommonConfig, TrendMomentumStrategyBase


@dataclass(frozen=True)
class TSMOMDonchianConfig(TrendCommonConfig):
    breakout_window: int = 55

    @classmethod
    def from_dict(cls, data: dict) -> "TSMOMDonchianConfig":
        return cls(**data)


class TSMOMDonchianStrategy(TrendMomentumStrategyBase):
    def __init__(self, config: TSMOMDonchianConfig) -> None:
        if config.breakout_window < 2:
            raise ValueError("breakout_window must be >= 2")
        super().__init__(config)

    def _is_ready(self) -> bool:
        return len(self._mid_close) > self.config.breakout_window

    def _compute_signal(self) -> Signal:
        if not self._is_ready():
            return None

        prior_high = max(self._mid_high[-(self.config.breakout_window + 1) : -1])
        prior_low = min(self._mid_low[-(self.config.breakout_window + 1) : -1])
        latest_close = self._mid_close[-1]
        if latest_close > prior_high:
            return "long"
        if latest_close < prior_low:
            return "short"
        return None

    def should_exit_position(
        self,
        bar: pd.Series,
        position: Position,
    ) -> bool:
        if position.side == "long":
            return self._latest_signal == "short"
        return self._latest_signal == "long"
