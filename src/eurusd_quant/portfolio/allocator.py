from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AllocationConfig:
    weighting_method: str = "equal_weight"
    max_weight_per_strategy: float = 1.0
    rebalance_frequency: str = "monthly"
    lookback_days: int = 63


def _normalize_weights(weights: pd.Series) -> pd.Series:
    total = float(weights.sum())
    if total <= 0:
        return pd.Series(0.0, index=weights.index)
    return weights / total


def _apply_weight_cap(weights: pd.Series, max_weight: float) -> pd.Series:
    if max_weight <= 0:
        raise ValueError("max_weight_per_strategy must be positive")
    if weights.empty:
        return weights

    capped = weights.copy().astype(float)
    remaining = capped.index.tolist()
    frozen: dict[str, float] = {}
    while remaining:
        subset = _normalize_weights(capped.loc[remaining])
        breached = subset[subset > max_weight]
        if breached.empty:
            for key, value in subset.items():
                frozen[key] = float(value)
            break
        for key in breached.index:
            frozen[key] = max_weight
        remaining = [key for key in remaining if key not in breached.index]
        residual = 1.0 - sum(frozen.values())
        if residual <= 0 or not remaining:
            for key in remaining:
                frozen[key] = 0.0
            break
        capped.loc[remaining] = _normalize_weights(capped.loc[remaining]) * residual

    out = pd.Series(frozen).reindex(weights.index).fillna(0.0)
    return _normalize_weights(out)


def compute_target_weights(pnl_history: pd.DataFrame, config: AllocationConfig) -> pd.Series:
    if pnl_history.empty:
        return pd.Series(dtype=float)

    columns = list(pnl_history.columns)
    if config.weighting_method == "equal_weight":
        weights = pd.Series(1.0, index=columns, dtype=float)
    elif config.weighting_method in {"inverse_vol", "capped_inverse_vol"}:
        history = pnl_history.tail(config.lookback_days) if config.lookback_days > 0 else pnl_history
        vols = history.std(ddof=0).astype(float)
        positive_vols = vols[vols > 0]
        floor = float(positive_vols.min()) * 0.5 if not positive_vols.empty else 1e-6
        adjusted_vols = vols.mask(vols <= 0, floor).fillna(floor)
        inverse = 1.0 / adjusted_vols
        if float(inverse.sum()) <= 0:
            weights = pd.Series(1.0, index=columns, dtype=float)
        else:
            weights = inverse.astype(float)
    else:
        raise ValueError(f"Unsupported weighting_method: {config.weighting_method}")

    normalized = _normalize_weights(weights)
    if config.weighting_method == "capped_inverse_vol" or config.max_weight_per_strategy < 1.0:
        return _apply_weight_cap(normalized, config.max_weight_per_strategy)
    return normalized
