from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.exits.atr_target_exit import ATRTargetExit
from eurusd_quant.exits.atr_trailing_exit import ATRTrailingExit
from eurusd_quant.exits.breakeven_atr_trailing_exit import BreakevenATRTrailingExit
from eurusd_quant.exits.retracement_exit import RetracementExit


def _bar(*, bid_high: float, ask_low: float) -> pd.Series:
    return pd.Series({"bid_high": bid_high, "ask_low": ask_low})


def test_retracement_target_initialization() -> None:
    model = RetracementExit(target_reversion_ratio=0.5)

    long_stop, long_tp, _ = model.initialize_position(
        side="long",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1010,
        context={"impulse_size": 0.0020},
    )
    short_stop, short_tp, _ = model.initialize_position(
        side="short",
        entry_price=1.1000,
        stop_loss=1.1010,
        take_profit=1.0990,
        context={"impulse_size": 0.0020},
    )

    assert long_stop == pytest.approx(1.0990)
    assert long_tp == pytest.approx(1.1010)
    assert short_stop == pytest.approx(1.1010)
    assert short_tp == pytest.approx(1.0990)


def test_atr_target_initialization() -> None:
    model = ATRTargetExit(atr_target_multiple=1.5)

    _, long_tp, _ = model.initialize_position(
        side="long",
        entry_price=1.2000,
        stop_loss=1.1990,
        take_profit=1.2010,
        context={"atr": 0.0010},
    )
    _, short_tp, _ = model.initialize_position(
        side="short",
        entry_price=1.2000,
        stop_loss=1.2010,
        take_profit=1.1990,
        context={"atr": 0.0010},
    )

    assert long_tp == pytest.approx(1.2015)
    assert short_tp == pytest.approx(1.1985)


def test_atr_trailing_stop_moves_only_in_favorable_direction() -> None:
    model = ATRTrailingExit(atr_trail_multiple=0.8, initial_stop_atr=1.0)
    state = {"best_price": 1.1000}

    stop_1, tp_1, state = model.update(
        side="long",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1050,
        bar=_bar(bid_high=1.1010, ask_low=1.0998),
        context={"atr": 0.0010},
        state=state,
    )
    assert stop_1 == pytest.approx(1.1002)

    stop_2, tp_2, state = model.update(
        side="long",
        entry_price=1.1000,
        stop_loss=stop_1,
        take_profit=tp_1,
        bar=_bar(bid_high=1.1005, ask_low=1.0996),
        context={"atr": 0.0010},
        state=state,
    )
    assert stop_2 == pytest.approx(stop_1)
    assert tp_2 == pytest.approx(tp_1)


def test_breakeven_trigger_moves_stop_to_entry_for_long() -> None:
    model = BreakevenATRTrailingExit(
        initial_stop_atr=1.0,
        breakeven_trigger_atr=0.5,
        trailing_start_atr=1.0,
        atr_trail_multiple=0.8,
    )
    state = {"best_price": 1.1000, "breakeven_set": False}

    stop, _, state = model.update(
        side="long",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1050,
        bar=_bar(bid_high=1.1006, ask_low=1.0998),
        context={"atr": 0.0010},
        state=state,
    )

    assert stop == pytest.approx(1.1000)
    assert state["breakeven_set"] is True


def test_breakeven_and_trailing_updates_for_short() -> None:
    model = BreakevenATRTrailingExit(
        initial_stop_atr=1.0,
        breakeven_trigger_atr=0.5,
        trailing_start_atr=1.0,
        atr_trail_multiple=0.8,
    )
    state = {"best_price": 1.2000, "breakeven_set": False}

    stop_1, tp_1, state = model.update(
        side="short",
        entry_price=1.2000,
        stop_loss=1.2010,
        take_profit=1.1950,
        bar=_bar(bid_high=1.2002, ask_low=1.1994),
        context={"atr": 0.0010},
        state=state,
    )
    assert stop_1 == pytest.approx(1.2000)
    assert state["breakeven_set"] is True

    stop_2, _, state = model.update(
        side="short",
        entry_price=1.2000,
        stop_loss=stop_1,
        take_profit=tp_1,
        bar=_bar(bid_high=1.1995, ask_low=1.1988),
        context={"atr": 0.0010},
        state=state,
    )
    assert stop_2 < stop_1
