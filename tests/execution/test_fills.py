from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.execution.fills import (
    compute_entry_fill_price,
    long_stop_triggered,
    long_take_profit_triggered,
    short_stop_triggered,
    short_take_profit_triggered,
)


def test_long_entry_fills_at_ask_open_plus_slippage() -> None:
    bar = pd.Series({"ask_open": 1.10020, "bid_open": 1.10010})
    fill = compute_entry_fill_price("long", bar, market_slippage_pips=0.1, pip_size=0.0001)
    assert fill == pytest.approx(1.10021)


def test_short_entry_fills_at_bid_open_minus_slippage() -> None:
    bar = pd.Series({"ask_open": 1.10020, "bid_open": 1.10010})
    fill = compute_entry_fill_price("short", bar, market_slippage_pips=0.1, pip_size=0.0001)
    assert fill == pytest.approx(1.10009)


def test_long_stop_triggers_on_bid_low() -> None:
    bar = pd.Series({"bid_low": 1.09900})
    assert long_stop_triggered(bar, stop_loss=1.09910)


def test_short_stop_triggers_on_ask_high() -> None:
    bar = pd.Series({"ask_high": 1.10150})
    assert short_stop_triggered(bar, stop_loss=1.10100)


def test_long_take_profit_triggers_on_bid_high() -> None:
    bar = pd.Series({"bid_high": 1.10200})
    assert long_take_profit_triggered(bar, take_profit=1.10190)


def test_short_take_profit_triggers_on_ask_low() -> None:
    bar = pd.Series({"ask_low": 1.09800})
    assert short_take_profit_triggered(bar, take_profit=1.09810)
