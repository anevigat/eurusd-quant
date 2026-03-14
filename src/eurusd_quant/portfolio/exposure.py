from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ExposureConfig:
    max_weight_per_pair: float | None = None
    max_usd_direction_exposure: float | None = None
    max_active_strategies_per_pair: int | None = None
    one_strategy_per_pair: bool = False
    blocked_strategy_pairs: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def infer_usd_direction(pair: str, side: str) -> str | None:
    normalized_pair = str(pair or "").upper()
    normalized_side = str(side or "").lower()
    if len(normalized_pair) != 6 or normalized_side not in {"long", "short"}:
        return None
    base = normalized_pair[:3]
    quote = normalized_pair[3:]
    if base == "USD":
        return "usd_long" if normalized_side == "long" else "usd_short"
    if quote == "USD":
        return "usd_short" if normalized_side == "long" else "usd_long"
    return None


def apply_exposure_caps(
    target_weights: pd.Series,
    active_positions: pd.DataFrame,
    config: ExposureConfig,
) -> pd.Series:
    weights = target_weights.copy().astype(float)
    if weights.empty:
        return weights
    if active_positions.empty:
        return pd.Series(0.0, index=weights.index, dtype=float)

    active_members = set(active_positions["member_name"].unique())
    weights.loc[~weights.index.isin(active_members)] = 0.0
    active_unique = active_positions.drop_duplicates(subset=["member_name", "pair", "usd_direction"])

    pair_limit = 1 if config.one_strategy_per_pair else config.max_active_strategies_per_pair
    if pair_limit is not None and pair_limit > 0:
        for pair, group in active_unique.groupby("pair", sort=True):
            members = sorted(group["member_name"].unique(), key=lambda name: (-weights.get(name, 0.0), name))
            for member_name in members[pair_limit:]:
                weights.loc[member_name] = 0.0

    for member_a, member_b in config.blocked_strategy_pairs:
        if weights.get(member_a, 0.0) <= 0 or weights.get(member_b, 0.0) <= 0:
            continue
        loser = member_b if weights[member_a] >= weights[member_b] else member_a
        weights.loc[loser] = 0.0

    if config.max_weight_per_pair is not None:
        for pair, group in active_unique.groupby("pair", sort=True):
            members = [name for name in group["member_name"].unique() if weights.get(name, 0.0) > 0]
            if not members:
                continue
            total = float(weights.loc[members].sum())
            if total > config.max_weight_per_pair:
                weights.loc[members] = weights.loc[members] * (config.max_weight_per_pair / total)

    if config.max_usd_direction_exposure is not None:
        for usd_direction, group in active_unique.groupby("usd_direction", sort=True):
            if usd_direction not in {"usd_long", "usd_short"}:
                continue
            members = [name for name in group["member_name"].unique() if weights.get(name, 0.0) > 0]
            if not members:
                continue
            total = float(weights.loc[members].sum())
            if total > config.max_usd_direction_exposure:
                weights.loc[members] = weights.loc[members] * (config.max_usd_direction_exposure / total)

    return weights.clip(lower=0.0)
