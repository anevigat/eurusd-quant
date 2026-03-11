from __future__ import annotations

import pytest

from eurusd_quant.utils import infer_pip_size, normalize_symbol, pips_to_price, price_to_pips


def test_normalize_symbol_uppercase() -> None:
    assert normalize_symbol("eurusd") == "EURUSD"


def test_infer_pip_size_non_jpy_pairs() -> None:
    assert infer_pip_size("EURUSD") == pytest.approx(0.0001)
    assert infer_pip_size("GBPUSD") == pytest.approx(0.0001)


def test_infer_pip_size_jpy_pairs() -> None:
    assert infer_pip_size("USDJPY") == pytest.approx(0.01)


def test_pips_to_price_conversion() -> None:
    assert pips_to_price("EURUSD", 10) == pytest.approx(0.001)
    assert pips_to_price("USDJPY", 10) == pytest.approx(0.1)


def test_price_to_pips_conversion() -> None:
    assert price_to_pips("EURUSD", 0.001) == pytest.approx(10)
    assert price_to_pips("USDJPY", 0.1) == pytest.approx(10)
