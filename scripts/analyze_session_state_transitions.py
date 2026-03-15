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

from eurusd_quant.research.session_state_transitions import (
    build_session_state_inventory,
    build_three_session_patterns,
    build_two_session_transitions,
    summarize_next_session_outcomes,
    summarize_pair_transition_comparison,
    summarize_three_session_patterns,
    summarize_two_session_transitions,
)


PAIR_FILES = {
    "EURUSD": "eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD": "gbpusd_bars_15m_2018_2024.parquet",
    "USDJPY": "usdjpy_bars_15m_2018_2024.parquet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze multi-session state transitions across FX pairs.")
    parser.add_argument(
        "--bars-root",
        type=Path,
        default=None,
        help="Directory containing 15m pair bar parquet files. Defaults to local data/bars/15m or the sibling main checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/session_state_transitions"),
        help="Directory where session-state transition outputs will be written.",
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


def add_pooled_summary(frame: pd.DataFrame, summary_fn):
    pooled = summary_fn(frame.assign(pair="ALL"))
    base = summary_fn(frame)
    return pd.concat([base, pooled], ignore_index=True)


def main() -> None:
    args = parse_args()
    bars_root = resolve_bars_root(args.bars_root)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    state_frames: list[pd.DataFrame] = []
    dataset_notes: dict[str, object] = {}

    for pair, filename in PAIR_FILES.items():
        path = bars_root / filename
        bars = load_pair_bars(path)
        states = build_session_state_inventory(
            bars,
            pair=pair,
            lookback_sessions=args.lookback_sessions,
            min_history=args.min_history,
        )
        state_frames.append(states)
        dataset_notes[pair] = {
            "path": str(path),
            "rows": int(len(bars)),
            "session_count": int(len(states)),
            "start_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).min().isoformat(),
            "end_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).max().isoformat(),
        }

    session_state_inventory = pd.concat(state_frames, ignore_index=True).sort_values(["pair", "session_start"])
    two_session_transitions = build_two_session_transitions(session_state_inventory)
    three_session_patterns = build_three_session_patterns(session_state_inventory)

    two_session_transition_summary = add_pooled_summary(two_session_transitions, summarize_two_session_transitions)
    three_session_pattern_summary = add_pooled_summary(three_session_patterns, summarize_three_session_patterns)
    next_session_outcomes_by_pattern = add_pooled_summary(three_session_patterns, summarize_next_session_outcomes)
    pair_transition_comparison = summarize_pair_transition_comparison(three_session_patterns, two_session_transitions)

    session_state_inventory.to_csv(output_dir / "session_state_inventory.csv", index=False, float_format="%.8g")
    two_session_transition_summary.to_csv(
        output_dir / "two_session_transition_summary.csv", index=False, float_format="%.8g"
    )
    three_session_pattern_summary.to_csv(
        output_dir / "three_session_pattern_summary.csv", index=False, float_format="%.8g"
    )
    next_session_outcomes_by_pattern.to_csv(
        output_dir / "next_session_outcomes_by_pattern.csv", index=False, float_format="%.8g"
    )
    pair_transition_comparison.to_csv(
        output_dir / "pair_transition_comparison.csv", index=False, float_format="%.8g"
    )

    notes = {
        "timeframe": "15m",
        "session_state_direction_flat_threshold": 1e-6,
        "session_state_breach_definition": "dominant breach within a session is the event with the largest breach_magnitude_atr",
        "transition_model": "adjacent completed sessions in the expected FX session order",
        "three_session_pattern_model": "previous session state + current session state -> next session outcome",
        "datasets": dataset_notes,
    }
    (output_dir / "transition_pattern_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")

    print(f"Saved session-state transition diagnostics to {output_dir}")
    print(pair_transition_comparison.to_string(index=False))


if __name__ == "__main__":
    main()
