from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eurusd_quant.strategies.asian_range_compression_breakout import (
    AsianRangeCompressionBreakoutConfig,
    AsianRangeCompressionBreakoutStrategy,
)
from eurusd_quant.strategies.atr_spike_new_high_low import (
    ATRSpikeNewHighLowConfig,
    ATRSpikeNewHighLowStrategy,
)
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.strategies.compression_breakout import (
    CompressionBreakoutConfig,
    CompressionBreakoutStrategy,
)
from eurusd_quant.strategies.compression_breakout_continuation import (
    CompressionBreakoutContinuationConfig,
    CompressionBreakoutContinuationStrategy,
)
from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)
from eurusd_quant.strategies.head_shoulders_reversal import (
    HeadShouldersReversalConfig,
    HeadShouldersReversalStrategy,
)
from eurusd_quant.strategies.impulse_session_open import (
    ImpulseSessionOpenConfig,
    ImpulseSessionOpenStrategy,
)
from eurusd_quant.strategies.london_open_impulse_fade import (
    LondonOpenImpulseFadeConfig,
    LondonOpenImpulseFadeStrategy,
)
from eurusd_quant.strategies.london_pullback_continuation import (
    LondonPullbackContinuationConfig,
    LondonPullbackContinuationStrategy,
)
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)
from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy
from eurusd_quant.strategies.trend_exhaustion_reversal import (
    TrendExhaustionReversalConfig,
    TrendExhaustionReversalStrategy,
)
from eurusd_quant.strategies.volatility_expansion_after_compression import (
    VolatilityExpansionAfterCompressionConfig,
    VolatilityExpansionAfterCompressionStrategy,
)
from eurusd_quant.strategies.vwap_intraday_reversion import (
    VWAPIntradayReversionConfig,
    VWAPIntradayReversionStrategy,
)
from eurusd_quant.strategies.vwap_session_open import (
    VWAPSessionOpenConfig,
    VWAPSessionOpenStrategy,
)


@dataclass(frozen=True)
class StrategyDefinition:
    config_class: type[Any]
    strategy_class: type[BaseStrategy]


STRATEGY_REGISTRY: dict[str, StrategyDefinition] = {
    "asian_range_compression_breakout": StrategyDefinition(
        config_class=AsianRangeCompressionBreakoutConfig,
        strategy_class=AsianRangeCompressionBreakoutStrategy,
    ),
    "atr_spike_new_high_low": StrategyDefinition(
        config_class=ATRSpikeNewHighLowConfig,
        strategy_class=ATRSpikeNewHighLowStrategy,
    ),
    "compression_breakout": StrategyDefinition(
        config_class=CompressionBreakoutConfig,
        strategy_class=CompressionBreakoutStrategy,
    ),
    "compression_breakout_continuation": StrategyDefinition(
        config_class=CompressionBreakoutContinuationConfig,
        strategy_class=CompressionBreakoutContinuationStrategy,
    ),
    "false_breakout_reversal": StrategyDefinition(
        config_class=FalseBreakoutReversalConfig,
        strategy_class=FalseBreakoutReversalStrategy,
    ),
    "head_shoulders_reversal": StrategyDefinition(
        config_class=HeadShouldersReversalConfig,
        strategy_class=HeadShouldersReversalStrategy,
    ),
    "impulse_session_open": StrategyDefinition(
        config_class=ImpulseSessionOpenConfig,
        strategy_class=ImpulseSessionOpenStrategy,
    ),
    "london_open_impulse_fade": StrategyDefinition(
        config_class=LondonOpenImpulseFadeConfig,
        strategy_class=LondonOpenImpulseFadeStrategy,
    ),
    "london_pullback_continuation": StrategyDefinition(
        config_class=LondonPullbackContinuationConfig,
        strategy_class=LondonPullbackContinuationStrategy,
    ),
    "ny_impulse_mean_reversion": StrategyDefinition(
        config_class=NYImpulseMeanReversionConfig,
        strategy_class=NYImpulseMeanReversionStrategy,
    ),
    "session_breakout": StrategyDefinition(
        config_class=SessionBreakoutConfig,
        strategy_class=SessionRangeBreakoutStrategy,
    ),
    "trend_exhaustion_reversal": StrategyDefinition(
        config_class=TrendExhaustionReversalConfig,
        strategy_class=TrendExhaustionReversalStrategy,
    ),
    "volatility_expansion_after_compression": StrategyDefinition(
        config_class=VolatilityExpansionAfterCompressionConfig,
        strategy_class=VolatilityExpansionAfterCompressionStrategy,
    ),
    "vwap_intraday_reversion": StrategyDefinition(
        config_class=VWAPIntradayReversionConfig,
        strategy_class=VWAPIntradayReversionStrategy,
    ),
    "vwap_session_open": StrategyDefinition(
        config_class=VWAPSessionOpenConfig,
        strategy_class=VWAPSessionOpenStrategy,
    ),
}


def get_strategy_definition(strategy_name: str) -> StrategyDefinition:
    if strategy_name not in STRATEGY_REGISTRY:
        supported = ", ".join(sorted(STRATEGY_REGISTRY))
        raise ValueError(f"Unsupported strategy '{strategy_name}'. Supported strategies: {supported}")
    return STRATEGY_REGISTRY[strategy_name]


def build_strategy(strategy_name: str, config_values: dict[str, Any]) -> BaseStrategy:
    definition = get_strategy_definition(strategy_name)
    config = definition.config_class.from_dict(config_values)
    return definition.strategy_class(config)
