from __future__ import annotations

from eurusd_quant.live.base_strategy import LiveStrategy

STRATEGY_REGISTRY: dict[str, type[LiveStrategy]] = {}


def register_strategy(name: str, strategy_class: type[LiveStrategy]) -> None:
    STRATEGY_REGISTRY[name] = strategy_class


def get_strategy(name: str) -> type[LiveStrategy]:
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy '{name}'. Available: [{available}]")
    return STRATEGY_REGISTRY[name]


def list_strategies() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


from eurusd_quant.live.strategies.ny_impulse_live import NYImpulseLiveStrategy

register_strategy("ny_impulse_mean_reversion", NYImpulseLiveStrategy)
