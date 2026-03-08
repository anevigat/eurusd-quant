from __future__ import annotations

import pandas as pd


def pips_to_price(pips: float, pip_size: float) -> float:
    return pips * pip_size


def compute_entry_fill_price(
    side: str,
    bar: pd.Series,
    market_slippage_pips: float,
    pip_size: float,
) -> float:
    slip = pips_to_price(market_slippage_pips, pip_size)
    if side == "long":
        return float(bar["ask_open"]) + slip
    if side == "short":
        return float(bar["bid_open"]) - slip
    raise ValueError(f"Unsupported side: {side}")


def long_stop_triggered(bar: pd.Series, stop_loss: float) -> bool:
    return float(bar["bid_low"]) <= stop_loss


def short_stop_triggered(bar: pd.Series, stop_loss: float) -> bool:
    return float(bar["ask_high"]) >= stop_loss


def long_take_profit_triggered(bar: pd.Series, take_profit: float) -> bool:
    return float(bar["bid_high"]) >= take_profit


def short_take_profit_triggered(bar: pd.Series, take_profit: float) -> bool:
    return float(bar["ask_low"]) <= take_profit


def compute_stop_fill_price(side: str, stop_loss: float, stop_slippage_pips: float, pip_size: float) -> float:
    slip = pips_to_price(stop_slippage_pips, pip_size)
    if side == "long":
        return stop_loss - slip
    if side == "short":
        return stop_loss + slip
    raise ValueError(f"Unsupported side: {side}")


def compute_market_exit_price(side: str, bar: pd.Series) -> float:
    if side == "long":
        return float(bar["bid_close"])
    if side == "short":
        return float(bar["ask_close"])
    raise ValueError(f"Unsupported side: {side}")
