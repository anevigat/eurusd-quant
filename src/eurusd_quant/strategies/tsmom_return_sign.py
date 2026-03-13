from __future__ import annotations

from dataclasses import dataclass

from eurusd_quant.strategies.tsmom_common import Signal, TrendCommonConfig, TrendMomentumStrategyBase


@dataclass(frozen=True)
class TSMOMReturnSignConfig(TrendCommonConfig):
    lookback_window: int = 60
    return_threshold: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "TSMOMReturnSignConfig":
        return cls(**data)


class TSMOMReturnSignStrategy(TrendMomentumStrategyBase):
    def __init__(self, config: TSMOMReturnSignConfig) -> None:
        if config.lookback_window < 1:
            raise ValueError("lookback_window must be >= 1")
        if config.return_threshold < 0:
            raise ValueError("return_threshold must be >= 0")
        super().__init__(config)

    def _is_ready(self) -> bool:
        return len(self._mid_close) > self.config.lookback_window

    def _compute_signal(self) -> Signal:
        if not self._is_ready():
            return None

        base_close = self._mid_close[-(self.config.lookback_window + 1)]
        if base_close == 0.0:
            return None
        trailing_return = (self._mid_close[-1] / base_close) - 1.0
        if trailing_return > self.config.return_threshold:
            return "long"
        if trailing_return < -self.config.return_threshold:
            return "short"
        return None
