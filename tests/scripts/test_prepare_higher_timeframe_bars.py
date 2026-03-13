from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "prepare_higher_timeframe_bars.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("prepare_higher_timeframe_bars", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load higher timeframe aggregation script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bar(timestamp: str, price: float, *, high: float | None = None, low: float | None = None) -> dict[str, object]:
    return {
        "timestamp": pd.Timestamp(timestamp, tz="UTC"),
        "symbol": "EURUSD",
        "timeframe": "15m",
        "bid_open": price,
        "bid_high": high if high is not None else price + 0.0004,
        "bid_low": low if low is not None else price - 0.0004,
        "bid_close": price + 0.0002,
        "ask_open": price + 0.0001,
        "ask_high": (high if high is not None else price + 0.0004) + 0.0001,
        "ask_low": (low if low is not None else price - 0.0004) + 0.0001,
        "ask_close": price + 0.0003,
        "mid_open": price + 0.00005,
        "mid_high": (high if high is not None else price + 0.0004) + 0.00005,
        "mid_low": (low if low is not None else price - 0.0004) + 0.00005,
        "mid_close": price + 0.00025,
        "spread_open": 0.0001,
        "spread_high": 0.0001,
        "spread_low": 0.0001,
        "spread_close": 0.0001,
        "session_label": "new_york" if pd.Timestamp(timestamp, tz="UTC").hour >= 13 else "asia",
    }


def test_daily_session_shift_changes_bucket_membership() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            make_bar("2024-01-01 21:45:00", 1.1000),
            make_bar("2024-01-01 22:00:00", 1.1100),
            make_bar("2024-01-02 21:45:00", 1.1200),
            make_bar("2024-01-02 22:00:00", 1.1300),
        ]
    )

    aggregated = module.aggregate_bars(bars, "1d", session_rollover_hour_utc=22)

    assert aggregated["timestamp"].tolist() == [
        pd.Timestamp("2023-12-31 22:00:00", tz="UTC"),
        pd.Timestamp("2024-01-01 22:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 22:00:00", tz="UTC"),
    ]
    assert aggregated["bid_open"].tolist() == [1.1000, 1.1100, 1.1300]
    assert aggregated["bid_close"].tolist() == pytest.approx([1.1002, 1.1202, 1.1302])


def test_daily_ohlc_aggregation_is_correct_under_shifted_resampling() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            make_bar("2024-01-01 22:00:00", 1.1000, high=1.1010, low=1.0990),
            make_bar("2024-01-01 22:15:00", 1.1005, high=1.1020, low=1.1000),
            make_bar("2024-01-02 21:45:00", 1.1010, high=1.1015, low=1.0985),
        ]
    )

    aggregated = module.aggregate_bars(bars, "1d", session_rollover_hour_utc=22)

    assert len(aggregated) == 1
    row = aggregated.iloc[0]
    assert row["timestamp"] == pd.Timestamp("2024-01-01 22:00:00", tz="UTC")
    assert row["timeframe"] == "1d"
    assert row["bid_open"] == 1.1000
    assert row["bid_close"] == 1.1012
    assert row["bid_high"] == 1.1020
    assert row["bid_low"] == 1.0985
    assert row["session_label"] == "new_york"


def test_four_hour_bars_align_with_session_anchor() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            make_bar("2024-01-01 21:45:00", 1.1000),
            make_bar("2024-01-01 22:00:00", 1.1010),
            make_bar("2024-01-01 23:45:00", 1.1020),
            make_bar("2024-01-02 01:45:00", 1.1030),
            make_bar("2024-01-02 02:00:00", 1.1040),
        ]
    )

    aggregated = module.aggregate_bars(bars, "4h", session_rollover_hour_utc=22)

    assert aggregated["timestamp"].tolist() == [
        pd.Timestamp("2024-01-01 18:00:00", tz="UTC"),
        pd.Timestamp("2024-01-01 22:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 02:00:00", tz="UTC"),
    ]
    assert aggregated["bid_open"].tolist() == [1.1000, 1.1010, 1.1040]
    assert aggregated["bid_close"].tolist() == pytest.approx([1.1002, 1.1032, 1.1042])


def test_default_rollover_hour_is_applied_consistently() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            make_bar("2024-01-01 21:45:00", 1.1000),
            make_bar("2024-01-01 22:00:00", 1.1100),
        ]
    )

    explicit = module.aggregate_bars(bars, "1d", session_rollover_hour_utc=22)
    defaulted = module.aggregate_bars(bars, "1d")

    pd.testing.assert_frame_equal(defaulted, explicit)


def test_no_dropped_or_duplicated_rows_beyond_bucket_boundaries() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            make_bar("2024-01-01 22:00:00", 1.1000),
            make_bar("2024-01-01 23:00:00", 1.1010),
            make_bar("2024-01-02 02:00:00", 1.1020),
            make_bar("2024-01-02 06:00:00", 1.1030),
            make_bar("2024-01-02 10:00:00", 1.1040),
            make_bar("2024-01-02 14:00:00", 1.1050),
            make_bar("2024-01-02 18:00:00", 1.1060),
        ]
    )

    aggregated = module.aggregate_bars(bars, "4h", session_rollover_hour_utc=22)

    assert len(aggregated) == 6
    assert aggregated["timestamp"].is_unique
    assert aggregated["timestamp"].tolist() == [
        pd.Timestamp("2024-01-01 22:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 02:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 06:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 10:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 14:00:00", tz="UTC"),
        pd.Timestamp("2024-01-02 18:00:00", tz="UTC"),
    ]


def test_invalid_rollover_hour_raises_clear_error() -> None:
    module = load_script_module()
    with pytest.raises(ValueError, match="between 0 and 23"):
        module.aggregate_bars(pd.DataFrame([make_bar("2024-01-01 22:00:00", 1.1000)]), "1d", session_rollover_hour_utc=24)


def test_metadata_file_path_and_payload(tmp_path: Path) -> None:
    module = load_script_module()
    output_path = tmp_path / "eurusd_bars_1d.parquet"
    metadata_path = module._metadata_path(output_path)

    assert metadata_path == tmp_path / "eurusd_bars_1d.metadata.json"

    payload = module.build_metadata(
        input_path=Path("/tmp/source.parquet"),
        timeframe="1d",
        session_rollover_hour_utc=22,
    )

    assert payload["source_file"] == "/tmp/source.parquet"
    assert payload["timeframe"] == "1d"
    assert payload["timestamp_timezone"] == "UTC"
    assert payload["timestamp_convention"] == "bar_open"
    assert payload["session_rollover_hour_utc"] == 22
    assert payload["session_alignment_mode"] == "fixed_utc_rollover"
    json.dumps(payload)
