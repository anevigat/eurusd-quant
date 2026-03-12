from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_event_strategy_sweep.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_event_strategy_sweep", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load event-strategy sweep module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_test_bars(num_bars: int = 120) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02 00:00:00+00:00", periods=num_bars, freq="15min")
    rows = []
    close = 1.1000
    for i, t in enumerate(ts):
        close += 0.00003
        if i % 15 == 0:
            close += 0.0010
        if i % 17 == 0:
            close -= 0.0009

        mid_close = close
        mid_open = mid_close - 0.00005
        mid_high = mid_close + 0.00020
        mid_low = mid_close - 0.00020
        spread = 0.00010
        half = spread / 2.0
        rows.append(
            {
                "timestamp": t,
                "symbol": "EURUSD",
                "timeframe": "15m",
                "bid_open": mid_open - half,
                "bid_high": mid_high - half,
                "bid_low": mid_low - half,
                "bid_close": mid_close - half,
                "ask_open": mid_open + half,
                "ask_high": mid_high + half,
                "ask_low": mid_low + half,
                "ask_close": mid_close + half,
                "mid_open": mid_open,
                "mid_high": mid_high,
                "mid_low": mid_low,
                "mid_close": mid_close,
                "spread_open": spread,
                "spread_high": spread,
                "spread_low": spread,
                "spread_close": spread,
                "session_label": "other",
            }
        )
    return pd.DataFrame(rows)


def test_grid_generation_count() -> None:
    module = load_script_module()
    grid = module.generate_grid(
        {
            "a": [1, 2],
            "b": [10, 20, 30],
            "c": ["x", "y"],
        }
    )
    assert len(grid) == 12


def test_config_selection_limit() -> None:
    module = load_script_module()
    configs = [{"id": i} for i in range(10)]
    selected = module.select_configs(configs, max_configs=3)
    assert len(selected) == 3
    assert selected[0]["id"] == 0
    assert selected[-1]["id"] == 9


def test_ranking_logic() -> None:
    module = load_script_module()
    df = pd.DataFrame(
        [
            {"config_id": "a", "total_trades": 150, "profit_factor": 1.2},
            {"config_id": "b", "total_trades": 80, "profit_factor": 2.0},
        ]
    )
    ranked = module.add_ranking(df, min_trades=100)
    expected_score = 1.2 * np.log(150)
    assert ranked.loc[ranked["config_id"] == "a", "score"].iloc[0] == pytest.approx(expected_score)
    assert np.isnan(ranked.loc[ranked["config_id"] == "b", "score"].iloc[0])


def test_result_recording_and_outputs(tmp_path: Path) -> None:
    module = load_script_module()
    bars = make_test_bars()
    bars_path = tmp_path / "bars.parquet"
    out_dir = tmp_path / "out"
    bars.to_parquet(bars_path, index=False)

    param_space = {
        "impulse_bars": [1, 2],
        "impulse_threshold_atr": [0.8],
        "entry_delay_bars": [0],
        "session_filter": ["none", "london"],
        "stop_atr": [1.0],
        "target_atr": [1.0],
        "max_hold_bars": [4],
    }

    ranked, top_configs, summary = module.run_sweep(
        bars_path=str(bars_path),
        output_dir=str(out_dir),
        max_configs=0,
        min_trades=1,
        param_space=param_space,
    )

    assert not ranked.empty
    assert isinstance(summary, dict)
    assert summary["executed_configs"] == 4
    assert (out_dir / "experiment_results.csv").exists()
    assert (out_dir / "top_configs.csv").exists()
    assert (out_dir / "summary.json").exists()

    payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert payload["total_grid_configs"] == 4
    assert payload["executed_configs"] == 4
    assert isinstance(top_configs, pd.DataFrame)
