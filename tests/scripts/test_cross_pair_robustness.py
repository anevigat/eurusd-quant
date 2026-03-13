from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

SWEEP_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_cross_pair_sweeps.py"
ROBUST_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "analyze_cross_pair_robustness.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_detect_available_datasets(tmp_path: Path) -> None:
    sweep = load_module(SWEEP_SCRIPT, "run_cross_pair_sweeps")
    eurusd_hist = tmp_path / "eurusd_bars_15m_2018_2024.parquet"
    eurusd_hist.touch()

    expected = {
        "EURUSD": {
            "historical": str(eurusd_hist),
            "forward": str(tmp_path / "eurusd_bars_15m_2025_now.parquet"),
        },
        "GBPUSD": {
            "historical": str(tmp_path / "gbpusd_bars_15m_2018_2024.parquet"),
        },
    }

    tasks, missing = sweep.detect_available_datasets(expected)
    assert len(tasks) == 1
    assert tasks[0].pair == "EURUSD"
    assert tasks[0].range_label == "historical"
    assert len(missing) == 2


def test_load_and_rank_across_pair_folders(tmp_path: Path) -> None:
    robust = load_module(ROBUST_SCRIPT, "analyze_cross_pair_robustness")
    input_root = tmp_path / "sweeps"
    a = input_root / "eurusd" / "historical"
    b = input_root / "gbpusd" / "historical"
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "config_id": "cfg_a",
                "profit_factor": 1.20,
                "total_trades": 200,
                "net_pnl": 0.01,
                "win_rate": 0.52,
                "max_drawdown": 0.02,
                "score_raw": 6.0,
                "ranking_score": 6.0,
            },
            {
                "config_id": "cfg_b",
                "profit_factor": 0.90,
                "total_trades": 250,
                "net_pnl": -0.01,
                "win_rate": 0.45,
                "max_drawdown": 0.04,
                "score_raw": 4.0,
                "ranking_score": 4.0,
            },
        ]
    ).to_csv(a / "experiment_results.csv", index=False)

    pd.DataFrame(
        [
            {
                "config_id": "cfg_a",
                "profit_factor": 1.05,
                "total_trades": 180,
                "net_pnl": 0.005,
                "win_rate": 0.50,
                "max_drawdown": 0.03,
                "score_raw": 5.0,
                "ranking_score": 5.0,
            },
            {
                "config_id": "cfg_b",
                "profit_factor": 0.80,
                "total_trades": 160,
                "net_pnl": -0.02,
                "win_rate": 0.40,
                "max_drawdown": 0.05,
                "score_raw": 3.0,
                "ranking_score": 3.0,
            },
        ]
    ).to_csv(b / "experiment_results.csv", index=False)

    all_results = robust.load_sweep_results(input_root)
    assert len(all_results) == 4
    assert set(all_results["pair"].unique()) == {"EURUSD", "GBPUSD"}

    pair_best = robust.build_pair_best_configs(all_results)
    assert len(pair_best) == 2
    assert (pair_best["best_config_id"] == "cfg_a").all()


def test_robustness_scoring_and_selection() -> None:
    robust = load_module(ROBUST_SCRIPT, "analyze_cross_pair_robustness")
    all_results = pd.DataFrame(
        [
            {
                "pair": "EURUSD",
                "range_label": "historical",
                "pair_range": "EURUSD_historical",
                "config_id": "cfg_a",
                "profit_factor": 1.10,
                "total_trades": 220,
                "net_pnl": 0.01,
                "win_rate": 0.52,
            },
            {
                "pair": "GBPUSD",
                "range_label": "historical",
                "pair_range": "GBPUSD_historical",
                "config_id": "cfg_a",
                "profit_factor": 1.05,
                "total_trades": 180,
                "net_pnl": 0.004,
                "win_rate": 0.51,
            },
            {
                "pair": "EURUSD",
                "range_label": "forward",
                "pair_range": "EURUSD_forward",
                "config_id": "cfg_a",
                "profit_factor": 0.98,
                "total_trades": 90,
                "net_pnl": 0.001,
                "win_rate": 0.50,
            },
            {
                "pair": "EURUSD",
                "range_label": "historical",
                "pair_range": "EURUSD_historical",
                "config_id": "cfg_bad",
                "profit_factor": 0.70,
                "total_trades": 350,
                "net_pnl": -0.03,
                "win_rate": 0.39,
            },
        ]
    )
    ranking = robust.compute_config_ranking(
        all_results,
        min_historical_trades=100,
        forward_pf_floor=0.95,
    )
    assert ranking.iloc[0]["config_id"] == "cfg_a"
    assert ranking.iloc[0]["robustness_score"] > ranking.iloc[1]["robustness_score"]

    selected = robust.select_robust_configs(ranking, min_pairs_supported=2)
    assert len(selected) == 1
    assert selected.iloc[0]["config_id"] == "cfg_a"
