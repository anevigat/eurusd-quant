from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_event_returns.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_event_returns", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load event-return analyzer module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_test_bars(num_bars: int = 96) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02 00:00:00+00:00", periods=num_bars, freq="15min")
    rows = []
    close = 1.1000
    for i, t in enumerate(ts):
        # Smooth baseline with a few structured shocks.
        close += 0.00003
        if i == 24:
            close += 0.0015  # strong up impulse
        if i == 44:
            close -= 0.0018  # strong down impulse / new low

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


def test_impulse_event_detection() -> None:
    module = load_script_module()
    bars = make_test_bars()
    events = module.detect_events(
        bars,
        impulse_lookback_bars=4,
        breakout_lookback_bars=20,
        compression_window_bars=40,
    )
    impulse_events = events[events["event_family"] == "impulse_events"]
    assert not impulse_events.empty
    assert (impulse_events["event_strength_atr"] >= 1.0).any()


def test_compression_bucket_assignment() -> None:
    module = load_script_module()
    assert module.compression_bucket(0.9, 0.9, 1.0, 1.1) == "<=p10"
    assert module.compression_bucket(0.95, 0.9, 1.0, 1.1) == "p10-p25"
    assert module.compression_bucket(1.05, 0.9, 1.0, 1.1) == "p25-p50"
    assert module.compression_bucket(1.2, 0.9, 1.0, 1.1) is None


def test_new_high_new_low_and_session_open_events() -> None:
    module = load_script_module()
    bars = make_test_bars()
    events = module.detect_events(
        bars,
        impulse_lookback_bars=4,
        breakout_lookback_bars=20,
        compression_window_bars=40,
    )
    names = set(events["event_name"].unique())
    assert "new_high_20" in names
    assert "new_low_20" in names
    assert "london_open" in names
    assert "new_york_open" in names


def test_forward_return_directional_normalization() -> None:
    module = load_script_module()
    closes = pd.Series([1.1000, 1.1005, 1.1010, 1.1015, 1.1020, 1.1025, 1.1030, 1.1035, 1.1040]).to_numpy()
    highs = closes + 0.0002
    lows = closes - 0.0002
    atr = pd.Series([0.0005] * len(closes)).to_numpy()

    up_metrics = module.compute_forward_metrics(closes, highs, lows, atr, idx=0, direction="up")
    down_metrics = module.compute_forward_metrics(closes, highs, lows, atr, idx=0, direction="down")
    assert up_metrics["return_4_bars"] > 0
    assert down_metrics["return_4_bars"] < 0


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    bars = make_test_bars()
    bars_path = tmp_path / "bars.parquet"
    out_dir = tmp_path / "out"
    bars.to_parquet(bars_path, index=False)

    module.run_analysis(
        bars_path=str(bars_path),
        output_dir=str(out_dir),
        atr_period=14,
        impulse_lookback_bars=4,
        breakout_lookback_bars=20,
        compression_window_bars=40,
        min_sample_size=5,
    )
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "event_returns.csv").exists()
    assert (out_dir / "event_bucket_summary.csv").exists()

