#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eurusd_quant.analytics.session_structure import (
    FX_SESSION_ROLLOVER_HOUR_UTC,
    SESSION_WINDOWS_UTC,
    build_session_records,
    ensure_session_columns,
)
from eurusd_quant.analytics.volatility_regimes import assign_time_aware_volatility_regimes
from eurusd_quant.research.structural_extremes import (
    FORWARD_RETURN_HORIZONS,
    STRUCTURAL_LOOKBACK_WINDOWS,
    build_extreme_event_inventory,
    summarize_context_behavior,
    summarize_post_extreme_forward_returns,
    summarize_sweep_vs_breakout,
)


PAIR_FILES = {
    "EURUSD": "eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD": "gbpusd_bars_15m_2018_2024.parquet",
    "USDJPY": "usdjpy_bars_15m_2018_2024.parquet",
}
LOW_SAMPLE_THRESHOLD = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze structural extremes and liquidity sweeps across FX pairs.")
    parser.add_argument(
        "--bars-root",
        type=Path,
        default=None,
        help="Directory containing 15m pair bar parquet files. Defaults to local data/bars/15m or the sibling main checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/structural_extremes"),
        help="Directory where structural-extremes outputs will be written.",
    )
    parser.add_argument(
        "--lookback-sessions",
        type=int,
        default=120,
        help="Trailing number of prior sessions used for time-aware volatility regime assignment.",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=30,
        help="Minimum prior sessions required before assigning a non-unknown volatility regime.",
    )
    return parser.parse_args()


def resolve_bars_root(explicit_root: Path | None) -> Path:
    candidates = []
    if explicit_root is not None:
        candidates.append(explicit_root)
    candidates.append(REPO_ROOT / "data" / "bars" / "15m")
    candidates.append(REPO_ROOT.parent / "eurusd_quant" / "data" / "bars" / "15m")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not resolve a bars root containing the 15m FX parquet datasets.")


def load_pair_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"timestamp", "mid_open", "mid_high", "mid_low", "mid_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return frame


def add_low_sample_flag(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "sample_count" in result.columns:
        result["low_sample"] = result["sample_count"] < LOW_SAMPLE_THRESHOLD
    return result


def add_pooled_rows(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    numeric_aggs: dict[str, str] = {}
    for column in frame.columns:
        if column in {"pair", *group_cols}:
            continue
        if column in {"sample_count", "bars_observed"}:
            numeric_aggs[column] = "sum"
        elif pd.api.types.is_numeric_dtype(frame[column]):
            numeric_aggs[column] = "mean"
    pooled = frame.groupby(group_cols, dropna=False).agg(numeric_aggs).reset_index()
    pooled.insert(0, "pair", "ALL")
    return pd.concat([frame, pooled], ignore_index=True)


def main() -> None:
    args = parse_args()
    bars_root = resolve_bars_root(args.bars_root)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pair_event_frames: list[pd.DataFrame] = []
    pair_bar_frames: list[pd.DataFrame] = []
    dataset_notes: dict[str, object] = {}

    for pair, filename in PAIR_FILES.items():
        path = bars_root / filename
        bars = load_pair_bars(path)
        labeled_bars = ensure_session_columns(bars)
        labeled_bars = labeled_bars.rename(columns={"session_label": "session"})
        labeled_bars["pair"] = pair
        labeled_bars["fx_session_date"] = pd.to_datetime(labeled_bars["fx_session_date"])

        session_records = build_session_records(bars, pair=pair)
        session_records = assign_time_aware_volatility_regimes(
            session_records,
            metric_col="realized_vol",
            lookback_sessions=args.lookback_sessions,
            min_history=args.min_history,
        )
        regime_map = session_records[["pair", "fx_session_date", "session", "volatility_regime"]].copy()
        labeled_bars = labeled_bars.merge(
            regime_map,
            on=["pair", "fx_session_date", "session"],
            how="left",
        )
        labeled_bars["volatility_regime"] = labeled_bars["volatility_regime"].astype("object").fillna("unknown")

        event_inventory = build_extreme_event_inventory(labeled_bars, pair=pair)
        pair_event_frames.append(event_inventory)
        pair_bar_frames.append(labeled_bars)

        dataset_notes[pair] = {
            "path": str(path),
            "rows": int(len(bars)),
            "start_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).min().isoformat(),
            "end_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).max().isoformat(),
            "event_count": int(len(event_inventory)),
        }

    all_bars = pd.concat(pair_bar_frames, ignore_index=True)
    extreme_event_inventory = pd.concat(pair_event_frames, ignore_index=True).sort_values(
        ["pair", "timestamp", "lookback_window", "event_type"]
    )
    sweep_event_inventory = extreme_event_inventory.loc[extreme_event_inventory["event_class"] == "sweep"].copy()

    post_extreme_forward_returns = add_low_sample_flag(
        add_pooled_rows(
            summarize_post_extreme_forward_returns(extreme_event_inventory),
            ["event_type", "lookback_window", "horizon_bars"],
        )
    )
    sweep_vs_breakout_summary = add_low_sample_flag(
        add_pooled_rows(
            summarize_sweep_vs_breakout(extreme_event_inventory),
            ["lookback_window", "event_class", "event_side", "horizon_bars"],
        )
    )
    session_sweep_behavior = add_low_sample_flag(
        add_pooled_rows(
            summarize_context_behavior(
                extreme_event_inventory,
                bars=all_bars,
                context_col="session",
                horizons=FORWARD_RETURN_HORIZONS,
            ),
            ["lookback_window", "event_type", "context_type", "context_value", "horizon_bars"],
        )
    )
    volatility_regime_sweep_behavior = add_low_sample_flag(
        add_pooled_rows(
            summarize_context_behavior(
                extreme_event_inventory,
                bars=all_bars,
                context_col="volatility_regime",
                horizons=FORWARD_RETURN_HORIZONS,
            ),
            ["lookback_window", "event_type", "context_type", "context_value", "horizon_bars"],
        )
    )

    extreme_event_inventory.to_csv(output_dir / "extreme_event_inventory.csv", index=False)
    sweep_event_inventory.to_csv(output_dir / "sweep_event_inventory.csv", index=False)
    post_extreme_forward_returns.to_csv(output_dir / "post_extreme_forward_returns.csv", index=False)
    sweep_vs_breakout_summary.to_csv(output_dir / "sweep_vs_breakout_summary.csv", index=False)
    session_sweep_behavior.to_csv(output_dir / "session_sweep_behavior.csv", index=False)
    volatility_regime_sweep_behavior.to_csv(output_dir / "volatility_regime_sweep_behavior.csv", index=False)

    notes = {
        "timeframe": "15m",
        "timestamp_convention": "UTC bar-open timestamps",
        "session_windows_utc": SESSION_WINDOWS_UTC,
        "session_rollover_hour_utc": FX_SESSION_ROLLOVER_HOUR_UTC,
        "lookback_windows_bars": list(STRUCTURAL_LOOKBACK_WINDOWS),
        "forward_return_horizons_bars": list(FORWARD_RETURN_HORIZONS),
        "volatility_regime_source": "R3 time-aware session realized-volatility buckets",
        "volatility_regime_lookback_sessions": args.lookback_sessions,
        "volatility_regime_min_history": args.min_history,
        "event_definitions": {
            "breakout_high": "mid_high exceeds the prior rolling high and the close remains at or above that prior high",
            "breakout_low": "mid_low falls below the prior rolling low and the close remains at or below that prior low",
            "sweep_high": "mid_high exceeds the prior rolling high but the close returns below that prior high",
            "sweep_low": "mid_low falls below the prior rolling low but the close returns above that prior low",
        },
        "low_sample_threshold": LOW_SAMPLE_THRESHOLD,
        "datasets": dataset_notes,
    }
    (output_dir / "extreme_analysis_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")

    print(f"Saved structural-extremes diagnostics to {output_dir}")
    print(sweep_vs_breakout_summary.head(18).to_string(index=False))


if __name__ == "__main__":
    main()
