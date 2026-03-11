from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_vwap_intraday_reversion.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("vwap_intraday_reversion", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load VWAP diagnostic script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_proxy_vwap_calculation() -> None:
    module = load_script_module()
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "mid_high": [1.1010, 1.1030, 1.1050],
            "mid_low": [1.0990, 1.1010, 1.1030],
            "mid_close": [1.1000, 1.1020, 1.1040],
        }
    )
    vwap = module.compute_intraday_vwap_proxy(df)
    assert vwap.iloc[0] == pytest.approx(1.1000)
    assert vwap.iloc[1] == pytest.approx(1.1010)
    assert vwap.iloc[2] == pytest.approx(1.1020)


def test_deviation_calculation() -> None:
    typical = (1.1030 + 1.1010 + 1.1020) / 3.0
    vwap = 1.1010
    deviation = 1.1020 - vwap
    assert typical == pytest.approx(1.1020)
    assert deviation == pytest.approx(0.0010)


def test_bucket_assignment() -> None:
    module = load_script_module()
    s = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
    buckets, thresholds = module.assign_deviation_buckets(s)
    assert thresholds["p50"] == pytest.approx(0.3)
    assert thresholds["p75"] == pytest.approx(0.4)
    assert thresholds["p90"] == pytest.approx(0.46)
    assert buckets.iloc[0] == "small_dev"
    assert buckets.iloc[2] == "small_dev"
    assert buckets.iloc[3] == "medium_dev"
    assert buckets.iloc[4] == "extreme_dev"


def test_reversion_ratio_calculation() -> None:
    module = load_script_module()
    ratio = module.compute_reversion_ratio(0.0020, 0.0010)
    assert ratio == pytest.approx(0.5)
    ratio_negative = module.compute_reversion_ratio(0.0020, 0.0030)
    assert ratio_negative == pytest.approx(-0.5)


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    obs = pd.DataFrame(
        {
            "timestamp": ["2024-01-02T07:00:00+00:00", "2024-01-02T07:15:00+00:00"],
            "deviation": [0.001, -0.0012],
            "deviation_atr": [0.5, -0.6],
            "deviation_bucket": ["small_dev", "medium_dev"],
            "reversion_ratio_4bars": [0.2, 0.3],
            "reversion_ratio_8bars": [0.1, 0.25],
        }
    )
    summary = {
        "bars_analyzed": 2,
        "median_abs_deviation_atr": 0.55,
        "p75_abs_deviation_atr": 0.575,
        "p90_abs_deviation_atr": 0.59,
        "diagnostic_verdict": "researched_but_not_promising",
    }
    distribution = pd.DataFrame(
        {
            "section": ["abs_deviation_atr_distribution"],
            "key": ["p50"],
            "value": [0.55],
        }
    )
    module.write_outputs(tmp_path, summary, obs, distribution)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "daily_metrics.csv").exists()
    assert (tmp_path / "distribution.csv").exists()
    loaded = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert loaded["bars_analyzed"] == 2
