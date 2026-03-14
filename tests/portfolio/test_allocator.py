from __future__ import annotations

import pandas as pd

from eurusd_quant.portfolio.allocator import AllocationConfig, compute_target_weights


def test_equal_weight_sums_to_one() -> None:
    history = pd.DataFrame({"a": [1.0, -0.5], "b": [0.2, 0.3], "c": [0.1, -0.2]})
    weights = compute_target_weights(history, AllocationConfig(weighting_method="equal_weight"))
    assert list(weights.index) == ["a", "b", "c"]
    assert weights.sum() == 1.0
    assert all(weight == 1.0 / 3.0 for weight in weights)


def test_inverse_vol_penalizes_higher_volatility() -> None:
    history = pd.DataFrame(
        {
            "low_vol": [0.01, 0.01, 0.01, 0.01],
            "high_vol": [0.10, -0.10, 0.10, -0.10],
        }
    )
    weights = compute_target_weights(history, AllocationConfig(weighting_method="inverse_vol"))
    assert weights["low_vol"] > weights["high_vol"]
    assert round(float(weights.sum()), 10) == 1.0


def test_weight_cap_is_respected() -> None:
    history = pd.DataFrame(
        {
            "stable": [0.01, 0.01, 0.01, 0.01],
            "noisy_a": [0.10, -0.10, 0.10, -0.10],
            "noisy_b": [0.09, -0.09, 0.09, -0.09],
        }
    )
    weights = compute_target_weights(
        history,
        AllocationConfig(weighting_method="capped_inverse_vol", max_weight_per_strategy=0.45),
    )
    assert weights.max() <= 0.45 + 1e-9
    assert round(float(weights.sum()), 10) == 1.0
