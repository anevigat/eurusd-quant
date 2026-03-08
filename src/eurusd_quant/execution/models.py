from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class Order:
    symbol: str
    timeframe: str
    side: str
    signal_time: pd.Timestamp
    entry_reference: float
    stop_loss: float
    take_profit: float
    max_holding_bars: int


@dataclass
class Position:
    side: str
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    bars_held: int
    max_holding_bars: int
    signal_time: pd.Timestamp
    entry_slippage_cost: float
    entry_spread_cost: float


@dataclass
class Trade:
    symbol: str
    side: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    exit_reason: str
    bars_held: int
    gross_pnl: float
    fee: float
    net_pnl: float
    pnl_pips: float
    slippage_cost: float
    spread_cost: float

    def to_dict(self) -> dict:
        return asdict(self)
