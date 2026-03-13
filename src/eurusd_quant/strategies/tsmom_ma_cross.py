from __future__ import annotations

from dataclasses import dataclass

from eurusd_quant.strategies.tsmom_common import Signal, TrendCommonConfig, TrendMomentumStrategyBase


@dataclass(frozen=True)
class TSMOMMACrossConfig(TrendCommonConfig):
    fast_window: int = 20
    slow_window: int = 100

    @classmethod
    def from_dict(cls, data: dict) -> "TSMOMMACrossConfig":
        return cls(**data)


class TSMOMMACrossStrategy(TrendMomentumStrategyBase):
    def __init__(self, config: TSMOMMACrossConfig) -> None:
        if config.fast_window < 1:
            raise ValueError("fast_window must be >= 1")
        if config.slow_window <= config.fast_window:
            raise ValueError("slow_window must be greater than fast_window")
        super().__init__(config)

    def _is_ready(self) -> bool:
        return len(self._mid_close) >= self.config.slow_window

    def _compute_signal(self) -> Signal:
        if not self._is_ready():
            return None
        fast_ma = sum(self._mid_close[-self.config.fast_window :]) / self.config.fast_window
        slow_ma = sum(self._mid_close[-self.config.slow_window :]) / self.config.slow_window
        if fast_ma > slow_ma:
            return "long"
        if fast_ma < slow_ma:
            return "short"
        return None
