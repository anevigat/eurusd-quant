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

from eurusd_quant.research.contextual_breaches import (
    CONTEXT_BOUNDARY_BARS,
    FORWARD_RETURN_HORIZONS,
    STRUCTURAL_LOOKBACK_WINDOWS,
    build_bar_context,
    build_contextual_breach_inventory,
    build_long_outcomes,
    summarize_contextual_outcomes,
)


PAIR_FILES = {
    "EURUSD": "eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD": "gbpusd_bars_15m_2018_2024.parquet",
    "USDJPY": "usdjpy_bars_15m_2018_2024.parquet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze contextual outcomes around structural breaches.")
    parser.add_argument(
        "--bars-root",
        type=Path,
        default=None,
        help="Directory containing 15m pair bar parquet files. Defaults to local data/bars/15m or the sibling main checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/contextual_breaches"),
        help="Directory where contextual breach outputs will be written.",
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


def add_pooled_rows(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    pooled = summarize_contextual_outcomes(frame.assign(pair="ALL"), ["pair", *group_cols])
    base = summarize_contextual_outcomes(frame, ["pair", *group_cols])
    return pd.concat([base, pooled], ignore_index=True).sort_values(["pair", *group_cols]).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    bars_root = resolve_bars_root(args.bars_root)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_frames: list[pd.DataFrame] = []
    outcome_frames: list[pd.DataFrame] = []
    dataset_notes: dict[str, object] = {}
    next_event_id = 1

    for pair, filename in PAIR_FILES.items():
        path = bars_root / filename
        bars = load_pair_bars(path)
        context_bars = build_bar_context(
            bars,
            pair=pair,
            lookback_sessions=args.lookback_sessions,
            min_history=args.min_history,
            boundary_bars=CONTEXT_BOUNDARY_BARS,
        )
        inventory, outcomes = build_contextual_breach_inventory(context_bars, pair=pair)
        if not inventory.empty:
            offset = next_event_id - 1
            inventory["event_id"] = inventory["event_id"] + offset
            outcomes["event_id"] = outcomes["event_id"] + offset
            next_event_id += len(inventory)

        inventory_frames.append(inventory)
        outcome_frames.append(outcomes)
        dataset_notes[pair] = {
            "path": str(path),
            "rows": int(len(bars)),
            "start_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).min().isoformat(),
            "end_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).max().isoformat(),
            "breach_count": int(len(inventory)),
        }

    contextual_breach_inventory = pd.concat(inventory_frames, ignore_index=True).sort_values(
        ["pair", "timestamp", "lookback_window", "event_type"]
    )
    contextual_breach_outcomes = pd.concat(outcome_frames, ignore_index=True).sort_values("event_id")
    long_outcomes = build_long_outcomes(contextual_breach_inventory, contextual_breach_outcomes)

    breach_outcomes_by_session_context = add_pooled_rows(
        long_outcomes,
        ["event_type", "lookback_window", "session", "session_subcontext", "transition_context", "horizon_bars"],
    )
    breach_outcomes_by_volatility_context = add_pooled_rows(
        long_outcomes,
        ["event_type", "lookback_window", "session", "volatility_regime", "horizon_bars"],
    )
    breach_outcomes_by_range_context = add_pooled_rows(
        long_outcomes,
        ["event_type", "lookback_window", "session", "range_regime", "horizon_bars"],
    )
    breach_outcomes_by_magnitude_bucket = add_pooled_rows(
        long_outcomes,
        ["event_type", "lookback_window", "magnitude_bucket", "horizon_bars"],
    )
    breach_outcomes_by_pair = summarize_contextual_outcomes(
        long_outcomes,
        ["pair", "event_type", "lookback_window", "horizon_bars"],
    )

    outcome_columns = ["event_id"]
    for horizon in FORWARD_RETURN_HORIZONS:
        outcome_columns.extend(
            [
                f"forward_return_{horizon}",
                f"aligned_forward_return_{horizon}",
                f"continuation_flag_{horizon}",
                f"reversal_flag_{horizon}",
                f"mfe_{horizon}",
                f"mae_{horizon}",
            ]
        )
    contextual_breach_outcomes_export = contextual_breach_outcomes[outcome_columns].copy()

    contextual_breach_inventory.to_csv(output_dir / "contextual_breach_inventory.csv", index=False, float_format="%.8g")
    contextual_breach_outcomes_export.to_csv(
        output_dir / "contextual_breach_outcomes.csv",
        index=False,
        float_format="%.8g",
    )
    breach_outcomes_by_session_context.to_csv(
        output_dir / "breach_outcomes_by_session_context.csv",
        index=False,
        float_format="%.8g",
    )
    breach_outcomes_by_volatility_context.to_csv(
        output_dir / "breach_outcomes_by_volatility_context.csv",
        index=False,
        float_format="%.8g",
    )
    breach_outcomes_by_range_context.to_csv(
        output_dir / "breach_outcomes_by_range_context.csv",
        index=False,
        float_format="%.8g",
    )
    breach_outcomes_by_magnitude_bucket.to_csv(
        output_dir / "breach_outcomes_by_magnitude_bucket.csv",
        index=False,
        float_format="%.8g",
    )
    breach_outcomes_by_pair.to_csv(output_dir / "breach_outcomes_by_pair.csv", index=False, float_format="%.8g")

    notes = {
        "timeframe": "15m",
        "lookback_windows_bars": list(STRUCTURAL_LOOKBACK_WINDOWS),
        "forward_return_horizons_bars": list(FORWARD_RETURN_HORIZONS),
        "boundary_bars": CONTEXT_BOUNDARY_BARS,
        "transition_context_definition": {
            "inside_asia": "Asia session bars",
            "asia_to_london_boundary": "first boundary bars of London session",
            "inside_london": "London bars after the opening boundary window",
            "london_to_new_york_boundary": "first boundary bars of New York session",
            "inside_new_york": "New York bars after the opening boundary window",
        },
        "magnitude_buckets": ["small", "medium", "large"],
        "volatility_regime_source": "R3 time-aware session realized-volatility buckets",
        "range_regime_source": "R2 trailing session-range baseline buckets",
        "datasets": dataset_notes,
    }
    (output_dir / "breach_context_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")

    print(f"Saved contextual breach diagnostics to {output_dir}")
    print(breach_outcomes_by_pair.head(18).to_string(index=False))


if __name__ == "__main__":
    main()
