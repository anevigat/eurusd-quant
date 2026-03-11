from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from eurusd_quant.data.sessions import parse_hhmm
from eurusd_quant.execution.ambiguity import resolve_exit_reason
from eurusd_quant.execution.fills import (
    compute_entry_fill_price,
    compute_market_exit_price,
    compute_stop_fill_price,
    long_stop_triggered,
    long_take_profit_triggered,
    short_stop_triggered,
    short_take_profit_triggered,
)
from eurusd_quant.execution.models import Order, Position, Trade


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str
    fill_on_next_open: bool
    ambiguity_mode: str
    market_slippage_pips: float
    stop_slippage_pips: float
    fee_per_trade: float
    pip_size: float
    max_positions_per_symbol: int
    flatten_intraday: bool
    flatten_time_utc: str
    reanchor_brackets_after_fill: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionConfig":
        return cls(**data)


class ExecutionSimulator:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self._flatten_time: time = parse_hhmm(config.flatten_time_utc)
        self._pending_order: Order | None = None
        self._position: Position | None = None
        self._trades: list[Trade] = []

    def submit_order(self, order: Order) -> None:
        if self._position is not None or self._pending_order is not None:
            raise ValueError("Only one position/order at a time is supported")
        self._pending_order = order

    def has_open_position(self) -> bool:
        return self._position is not None

    def has_pending_order(self) -> bool:
        return self._pending_order is not None

    def get_open_position(self) -> Position | None:
        return self._position

    def update_open_position_brackets(self, stop_loss: float, take_profit: float) -> None:
        if self._position is None:
            return
        self._position.stop_loss = float(stop_loss)
        self._position.take_profit = float(take_profit)

    def process_bar(self, bar: pd.Series) -> None:
        if self._pending_order is not None and self.config.fill_on_next_open:
            self._fill_pending_order(bar)
        if self._position is not None:
            self._evaluate_open_position(bar)

    def close_open_position_at_end(self, bar: pd.Series) -> None:
        if self._position is None:
            return
        exit_price = compute_market_exit_price(self._position.side, bar)
        self._close_position(bar, exit_price=exit_price, exit_reason="end_of_data")

    def get_trades_df(self) -> pd.DataFrame:
        rows = [trade.to_dict() for trade in self._trades]
        if not rows:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "side",
                    "signal_time",
                    "entry_time",
                    "exit_time",
                    "entry_price",
                    "exit_price",
                    "stop_loss",
                    "take_profit",
                    "exit_reason",
                    "bars_held",
                    "gross_pnl",
                    "fee",
                    "net_pnl",
                    "pnl_pips",
                    "slippage_cost",
                    "spread_cost",
                ]
            )
        return pd.DataFrame(rows)

    def _fill_pending_order(self, bar: pd.Series) -> None:
        assert self._pending_order is not None
        order = self._pending_order

        entry_price = compute_entry_fill_price(
            order.side,
            bar,
            market_slippage_pips=self.config.market_slippage_pips,
            pip_size=self.config.pip_size,
        )

        if self.config.reanchor_brackets_after_fill:
            risk_distance = abs(order.entry_reference - order.stop_loss)
            tp_distance = abs(order.take_profit - order.entry_reference)
            if order.side == "long":
                stop_loss = entry_price - risk_distance
                take_profit = entry_price + tp_distance
            else:
                stop_loss = entry_price + risk_distance
                take_profit = entry_price - tp_distance
        else:
            stop_loss = order.stop_loss
            take_profit = order.take_profit

        entry_slippage_cost = self.config.market_slippage_pips * self.config.pip_size
        entry_spread_cost = max(0.0, float(bar["ask_open"]) - float(bar["bid_open"]))

        self._position = Position(
            side=order.side,
            symbol=order.symbol,
            entry_time=bar["timestamp"],
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            bars_held=0,
            max_holding_bars=order.max_holding_bars,
            signal_time=order.signal_time,
            entry_slippage_cost=entry_slippage_cost,
            entry_spread_cost=entry_spread_cost,
        )
        self._pending_order = None

    def _evaluate_open_position(self, bar: pd.Series) -> None:
        assert self._position is not None
        self._position.bars_held += 1
        pos = self._position

        if pos.side == "long":
            stop_hit = long_stop_triggered(bar, pos.stop_loss)
            tp_hit = long_take_profit_triggered(bar, pos.take_profit)
        else:
            stop_hit = short_stop_triggered(bar, pos.stop_loss)
            tp_hit = short_take_profit_triggered(bar, pos.take_profit)

        exit_reason = resolve_exit_reason(stop_hit, tp_hit, mode=self.config.ambiguity_mode)
        if exit_reason == "stop_loss":
            exit_price = compute_stop_fill_price(
                pos.side,
                pos.stop_loss,
                stop_slippage_pips=self.config.stop_slippage_pips,
                pip_size=self.config.pip_size,
            )
            self._close_position(bar, exit_price=exit_price, exit_reason=exit_reason)
            return
        if exit_reason == "take_profit":
            self._close_position(bar, exit_price=pos.take_profit, exit_reason=exit_reason)
            return

        if self.config.flatten_intraday and bar["timestamp"].time() >= self._flatten_time:
            exit_price = compute_market_exit_price(pos.side, bar)
            self._close_position(bar, exit_price=exit_price, exit_reason="flatten_intraday")
            return

        if pos.bars_held >= pos.max_holding_bars:
            exit_price = compute_market_exit_price(pos.side, bar)
            self._close_position(bar, exit_price=exit_price, exit_reason="time_exit")

    def _close_position(self, bar: pd.Series, exit_price: float, exit_reason: str) -> None:
        assert self._position is not None
        pos = self._position

        if pos.side == "long":
            gross_pnl = exit_price - pos.entry_price
        else:
            gross_pnl = pos.entry_price - exit_price
        fee = self.config.fee_per_trade
        net_pnl = gross_pnl - fee
        pnl_pips = net_pnl / self.config.pip_size

        exit_slippage_cost = 0.0
        if exit_reason == "stop_loss":
            exit_slippage_cost = self.config.stop_slippage_pips * self.config.pip_size

        exit_spread_cost = 0.0
        if exit_reason in {"time_exit", "flatten_intraday", "end_of_data"}:
            # Approximation: include spread crossing on explicit market exits.
            exit_spread_cost = max(0.0, float(bar["ask_close"]) - float(bar["bid_close"]))

        slippage_cost = pos.entry_slippage_cost + exit_slippage_cost
        spread_cost = pos.entry_spread_cost + exit_spread_cost

        self._trades.append(
            Trade(
                symbol=pos.symbol,
                side=pos.side,
                signal_time=pos.signal_time,
                entry_time=pos.entry_time,
                exit_time=bar["timestamp"],
                entry_price=pos.entry_price,
                exit_price=exit_price,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                exit_reason=exit_reason,
                bars_held=pos.bars_held,
                gross_pnl=gross_pnl,
                fee=fee,
                net_pnl=net_pnl,
                pnl_pips=pnl_pips,
                slippage_cost=slippage_cost,
                spread_cost=spread_cost,
            )
        )
        self._position = None
