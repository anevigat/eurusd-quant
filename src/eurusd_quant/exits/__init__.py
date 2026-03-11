from __future__ import annotations

from typing import Any

from eurusd_quant.exits.atr_target_exit import ATRTargetExit
from eurusd_quant.exits.atr_trailing_exit import ATRTrailingExit
from eurusd_quant.exits.base_exit import ExitModel
from eurusd_quant.exits.breakeven_atr_trailing_exit import BreakevenATRTrailingExit
from eurusd_quant.exits.retracement_exit import RetracementExit


EXIT_MODEL_REGISTRY = {
    "retracement": RetracementExit,
    "atr": ATRTargetExit,
    "atr_trailing": ATRTrailingExit,
    "breakeven_atr_trailing": BreakevenATRTrailingExit,
}


def build_exit_model(name: str, params: dict[str, Any]) -> ExitModel:
    if name not in EXIT_MODEL_REGISTRY:
        raise ValueError(f"Unsupported exit model: {name}")
    cls = EXIT_MODEL_REGISTRY[name]
    return cls(**params)


__all__ = [
    "ExitModel",
    "RetracementExit",
    "ATRTargetExit",
    "ATRTrailingExit",
    "BreakevenATRTrailingExit",
    "build_exit_model",
]
