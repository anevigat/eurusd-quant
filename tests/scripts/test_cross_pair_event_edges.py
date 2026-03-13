from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_cross_pair_event_edges.py"


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_cross_pair_event_edges", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analyze_cross_pair_event_edges module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyze_cross_pair_event_edges"] = module
    spec.loader.exec_module(module)
    return module


def test_cross_pair_aggregation_logic(tmp_path: Path) -> None:
    module = load_module()
    input_root = tmp_path / "v2"
    datasets = ["EURUSD_historical", "GBPUSD_historical", "EURUSD_forward"]
    for label in datasets:
        d = input_root / label
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "combination_name": "impulse_x_session_open",
                    "direction": "up",
                    "bucket": "london_open",
                    "sample_size": 300,
                    "median_return_4_bars": 0.12,
                    "median_adverse_move_4_bars": 0.08,
                    "edge_score": 0.68,
                },
                {
                    "combination_name": "compression_x_new_high_low",
                    "direction": "down",
                    "bucket": "new_low_20",
                    "sample_size": 260,
                    "median_return_4_bars": -0.05,
                    "median_adverse_move_4_bars": 0.10,
                    "edge_score": 0.28,
                },
            ]
        ).to_csv(d / "top_combination_edges_v2.csv", index=False)

    out_dir = tmp_path / "cross_pair"
    top_edges, matrix, summary = module.run_cross_pair_analysis(input_root=input_root, output_dir=out_dir)
    assert not top_edges.empty
    assert not matrix.empty
    assert "EURUSD_historical" in summary["detected_datasets"]
    assert (out_dir / "cross_pair_top_edges.csv").exists()
    assert (out_dir / "cross_pair_edge_matrix.csv").exists()
    assert (out_dir / "cross_pair_summary.json").exists()
