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
    / "discover_event_edges.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("discover_event_edges", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load event-edge discovery module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_bucket_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_family": "impulse_events",
                "event_name": "impulse_4bar",
                "bucket": ">2.0_atr",
                "direction": "down",
                "sample_size": 1000,
                "median_return_4_bars": -0.08,
                "median_adverse_move_4_bars": 0.9,
            },
            {
                "event_family": "range_compression_events",
                "event_name": "atr_compression",
                "bucket": "<=p10",
                "direction": "none",
                "sample_size": 1200,
                "median_return_4_bars": 0.06,
                "median_adverse_move_4_bars": 1.3,
            },
            {
                "event_family": "new_high_low_events",
                "event_name": "new_high_20",
                "bucket": "all",
                "direction": "up",
                "sample_size": 250,
                "median_return_4_bars": -0.05,
                "median_adverse_move_4_bars": 0.8,
            },
            {
                "event_family": "session_open_events",
                "event_name": "london_open",
                "bucket": "all",
                "direction": "none",
                "sample_size": 50,
                "median_return_4_bars": 0.1,
                "median_adverse_move_4_bars": 2.0,
            },
        ]
    )


def test_edge_score_calculation() -> None:
    module = load_script_module()
    df = sample_bucket_summary()
    scored = module.compute_edge_score(df)
    row = scored.loc[scored["event_family"] == "impulse_events"].iloc[0]
    assert row["edge_score"] == pytest.approx(abs(-0.08) * np.log(1000))


def test_filtering_and_classification() -> None:
    module = load_script_module()
    df = sample_bucket_summary()
    scored = module.compute_edge_score(df)
    filtered = module.apply_min_sample_filter(scored, min_sample_size=200)
    continuation, reversal = module.split_continuation_reversal(filtered)
    assert (filtered["sample_size"] < 200).sum() == 0
    assert (continuation["median_return_4_bars"] > 0).all()
    assert (reversal["median_return_4_bars"] < 0).all()


def test_candidate_strategy_type_rules() -> None:
    module = load_script_module()
    assert module.infer_suggested_strategy_type("impulse_events", -0.1) == "impulse_fade"
    assert module.infer_suggested_strategy_type("range_compression_events", 0.1) == "volatility_breakout"
    assert module.infer_suggested_strategy_type("new_high_low_events", -0.1) == "breakout_failure"
    assert module.infer_suggested_strategy_type("session_open_events", 0.1) == "experimental"


def test_candidate_json_generation(tmp_path: Path) -> None:
    module = load_script_module()
    df = sample_bucket_summary()
    input_path = tmp_path / "bucket_summary.csv"
    out_dir = tmp_path / "out"
    df.to_csv(input_path, index=False)

    continuation, reversal, candidates = module.run_discovery(
        input_path=str(input_path),
        output_dir=str(out_dir),
        min_sample_size=200,
        top_n=5,
        candidate_count=3,
    )

    assert not continuation.empty
    assert not reversal.empty
    assert len(candidates) == 3
    payload = json.loads((out_dir / "edge_candidates.json").read_text(encoding="utf-8"))
    assert "candidates" in payload
    assert len(payload["candidates"]) == 3
