from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_event_combinations_v2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_event_combinations_v2", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analyze_event_combinations_v2 module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyze_event_combinations_v2"] = module
    spec.loader.exec_module(module)
    return module


def make_test_bars(num_bars: int = 180) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02 00:00:00+00:00", periods=num_bars, freq="15min")
    close = 1.1000
    rows = []
    for i, t in enumerate(ts):
        close += 0.00002
        if t.hour == 7 and t.minute == 0:
            close += 0.0015
        if t.hour == 13 and t.minute == 0:
            close -= 0.0013
        if i % 22 == 0:
            close += 0.0011
        if i % 31 == 0:
            close -= 0.0010

        mid_close = close
        mid_open = mid_close - 0.00005
        mid_high = mid_close + 0.00025
        mid_low = mid_close - 0.00025
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


def test_pairwise_combination_detection() -> None:
    module = load_module()
    bars = make_test_bars()
    features = module.build_feature_frame(bars)
    events = module.detect_pairwise_combinations(features, alignment_window_bars=1)
    assert not events.empty
    assert "impulse_x_session_open" in set(events["combination_name"])


def test_edge_score_and_quality_score() -> None:
    module = load_module()
    edge = module.compute_edge_score(0.2, 400)
    quality = module.compute_quality_score(0.2, 0.5)
    assert edge > 0
    assert quality == 0.4


def test_dataset_output_creation(tmp_path: Path) -> None:
    module = load_module()
    bars = make_test_bars()
    bars_path = tmp_path / "bars.parquet"
    bars.to_parquet(bars_path, index=False)

    summary = module.run_dataset_analysis(
        label="EURUSD_historical",
        path=bars_path,
        output_root=tmp_path / "out",
        alignment_window_bars=1,
        min_sample_size=10,
    )
    out_dir = tmp_path / "out" / "EURUSD_historical"
    assert summary["events_analyzed"] >= 0
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "event_combinations_v2.csv").exists()
    assert (out_dir / "combination_bucket_summary_v2.csv").exists()
    assert (out_dir / "top_combination_edges_v2.csv").exists()
    assert (out_dir / "top_conditional_edges_v2.csv").exists()
