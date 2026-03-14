from __future__ import annotations

import pandas as pd

from eurusd_quant.portfolio.exposure import ExposureConfig, apply_exposure_caps, infer_usd_direction


def test_same_pair_cap_is_enforced() -> None:
    weights = pd.Series({"a": 0.5, "b": 0.5, "c": 0.2})
    active = pd.DataFrame(
        [
            {"member_name": "a", "pair": "EURUSD", "usd_direction": "usd_short"},
            {"member_name": "b", "pair": "EURUSD", "usd_direction": "usd_short"},
            {"member_name": "c", "pair": "GBPUSD", "usd_direction": "usd_short"},
        ]
    )
    capped = apply_exposure_caps(weights, active, ExposureConfig(max_weight_per_pair=0.6))
    assert capped[["a", "b"]].sum() <= 0.6 + 1e-9


def test_same_usd_direction_cap_is_enforced() -> None:
    weights = pd.Series({"eur_long": 0.5, "gbp_long": 0.4})
    active = pd.DataFrame(
        [
            {"member_name": "eur_long", "pair": "EURUSD", "usd_direction": "usd_short"},
            {"member_name": "gbp_long", "pair": "GBPUSD", "usd_direction": "usd_short"},
        ]
    )
    capped = apply_exposure_caps(weights, active, ExposureConfig(max_usd_direction_exposure=0.6))
    assert capped.sum() <= 0.6 + 1e-9


def test_max_active_strategies_per_pair_keeps_highest_weight() -> None:
    weights = pd.Series({"a": 0.5, "b": 0.3, "c": 0.2})
    active = pd.DataFrame(
        [
            {"member_name": "a", "pair": "EURUSD", "usd_direction": "usd_short"},
            {"member_name": "b", "pair": "EURUSD", "usd_direction": "usd_short"},
            {"member_name": "c", "pair": "EURUSD", "usd_direction": "usd_short"},
        ]
    )
    capped = apply_exposure_caps(weights, active, ExposureConfig(max_active_strategies_per_pair=2))
    assert capped["a"] > 0
    assert capped["b"] > 0
    assert capped["c"] == 0


def test_infer_usd_direction_handles_base_and_quote() -> None:
    assert infer_usd_direction("EURUSD", "long") == "usd_short"
    assert infer_usd_direction("USDJPY", "long") == "usd_long"
    assert infer_usd_direction("GBPJPY", "long") is None
