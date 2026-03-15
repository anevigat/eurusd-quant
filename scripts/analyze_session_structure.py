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
    SESSION_ORDER,
    SESSION_WINDOWS_UTC,
    assign_regimes,
    build_distribution_summary,
    build_session_records,
    build_transition_records,
    summarize_session_behavior,
    summarize_transitions,
)


PAIR_FILES = {
    "EURUSD": "eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD": "gbpusd_bars_15m_2018_2024.parquet",
    "USDJPY": "usdjpy_bars_15m_2018_2024.parquet",
}
LOW_SAMPLE_THRESHOLD = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze descriptive session market structure across FX pairs.")
    parser.add_argument(
        "--bars-root",
        type=Path,
        default=None,
        help="Directory containing 15m pair bar parquet files. Defaults to local data/bars/15m or the sibling main checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/session_structure"),
        help="Directory where CSV and JSON outputs will be written.",
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
    if "timestamp" not in frame.columns:
        raise ValueError(f"{path} is missing a timestamp column.")
    required = {"mid_open", "mid_high", "mid_low", "mid_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required price columns: {sorted(missing)}")
    return frame


def add_sample_flags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "sample_count" in result.columns:
        result["low_sample"] = result["sample_count"] < LOW_SAMPLE_THRESHOLD
    return result


def build_normalized_summaries(session_records: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    regime_dimensions = ["volatility_regime", "range_regime", "extreme_regime"]
    for regime_dimension in regime_dimensions:
        pair_level = summarize_session_behavior(session_records, ["pair", "session", regime_dimension])
        pair_level = pair_level.rename(columns={regime_dimension: "regime_bucket"})
        pair_level.insert(0, "scope", "pair_session")
        pair_level.insert(3, "regime_dimension", regime_dimension)
        rows.append(pair_level)

        pooled = summarize_session_behavior(session_records, ["session", regime_dimension])
        pooled = pooled.rename(columns={regime_dimension: "regime_bucket"})
        pooled.insert(0, "scope", "pooled_session")
        pooled.insert(1, "pair", "ALL")
        pooled.insert(3, "regime_dimension", regime_dimension)
        rows.append(pooled)

    combined = pd.concat(rows, ignore_index=True)
    desired_cols = [
        "scope",
        "pair",
        "session",
        "regime_dimension",
        "regime_bucket",
        "avg_return",
        "median_return",
        "avg_abs_return",
        "avg_range",
        "continuation_prob",
        "reversal_prob",
        "bullish_frac",
        "bearish_frac",
        "realized_vol",
        "avg_directional_efficiency_ratio",
        "avg_close_location_value",
        "sample_count",
    ]
    return add_sample_flags(combined[desired_cols]).sort_values(
        ["scope", "pair", "session", "regime_dimension", "regime_bucket"]
    ).reset_index(drop=True)


def build_transition_summaries(session_records: pd.DataFrame) -> pd.DataFrame:
    transitions = build_transition_records(session_records)
    if transitions.empty:
        return pd.DataFrame()

    rows: list[pd.DataFrame] = []

    pair_sign = summarize_transitions(transitions, ["pair", "transition", "prior_session_sign"])
    pair_sign.insert(0, "scope", "pair")
    pair_sign["prior_volatility_regime"] = "all"
    rows.append(pair_sign)

    pooled_sign = summarize_transitions(transitions, ["transition", "prior_session_sign"])
    pooled_sign.insert(0, "scope", "pooled")
    pooled_sign.insert(1, "pair", "ALL")
    pooled_sign["prior_volatility_regime"] = "all"
    rows.append(pooled_sign)

    pair_vol = summarize_transitions(
        transitions,
        ["pair", "transition", "prior_session_sign", "prior_volatility_regime"],
    )
    pair_vol.insert(0, "scope", "pair_by_prior_vol")
    rows.append(pair_vol)

    pooled_vol = summarize_transitions(
        transitions,
        ["transition", "prior_session_sign", "prior_volatility_regime"],
    )
    pooled_vol.insert(0, "scope", "pooled_by_prior_vol")
    pooled_vol.insert(1, "pair", "ALL")
    rows.append(pooled_vol)

    combined = pd.concat(rows, ignore_index=True)
    desired_cols = [
        "scope",
        "pair",
        "transition",
        "prior_session_sign",
        "prior_volatility_regime",
        "continuation_prob",
        "reversal_prob",
        "avg_next_session_return",
        "avg_next_session_range",
        "sample_count",
    ]
    return add_sample_flags(combined[desired_cols]).sort_values(
        ["scope", "pair", "transition", "prior_session_sign", "prior_volatility_regime"]
    ).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    bars_root = resolve_bars_root(args.bars_root)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    session_frames: list[pd.DataFrame] = []
    dataset_notes: dict[str, object] = {}

    for pair, filename in PAIR_FILES.items():
        path = bars_root / filename
        bars = load_pair_bars(path)
        session_frame = build_session_records(bars, pair=pair)
        session_frames.append(session_frame)
        dataset_notes[pair] = {
            "path": str(path),
            "rows": int(len(bars)),
            "start_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).min().isoformat(),
            "end_timestamp_utc": pd.to_datetime(bars["timestamp"], utc=True).max().isoformat(),
            "session_count": int(len(session_frame)),
        }

    session_records = pd.concat(session_frames, ignore_index=True)
    session_records["session"] = pd.Categorical(
        session_records["session"],
        categories=list(SESSION_ORDER),
        ordered=True,
    )
    session_records = assign_regimes(session_records)

    session_summary_by_pair = add_sample_flags(
        summarize_session_behavior(session_records, ["pair", "session"])
    )
    pooled_cross_pair_summary = add_sample_flags(
        summarize_session_behavior(session_records, ["session"])
    )
    session_return_distribution = add_sample_flags(
        build_distribution_summary(session_records, ["pair", "session"])
    )
    normalized_behavior = build_normalized_summaries(session_records)
    session_transition_summary = build_transition_summaries(session_records)

    session_summary_by_pair.to_csv(output_dir / "session_summary_by_pair.csv", index=False)
    pooled_cross_pair_summary.to_csv(output_dir / "pooled_cross_pair_session_summary.csv", index=False)
    session_return_distribution.to_csv(output_dir / "session_return_distribution.csv", index=False)
    normalized_behavior.to_csv(output_dir / "normalized_behavior_by_regime.csv", index=False)
    session_transition_summary.to_csv(output_dir / "session_transition_summary.csv", index=False)

    summary_notes = {
        "timeframe": "15m",
        "timestamp_convention": "UTC bar-open timestamps",
        "session_rollover_hour_utc": FX_SESSION_ROLLOVER_HOUR_UTC,
        "session_windows_utc": SESSION_WINDOWS_UTC,
        "session_date_definition": "fx_session_date = (timestamp + 2h).date so the 22:00 UTC rollover starts a new FX trading date",
        "transition_pairs": ["asia_to_london", "london_to_new_york"],
        "volatility_regime_definition": "Within each pair+session, realized session volatility bucketed into low/medium/high quantile buckets.",
        "range_regime_definition": "Current session range divided by trailing 20-session median range for the same pair+session; <0.8 compressed, 0.8-1.2 normal, >1.2 expanded.",
        "extreme_regime_definition": "Bars since the last 15m bar with body >= 1.5 * ATR(14): <=8 recent_extreme, 9-32 intermediate, >32 stale.",
        "continuation_definition": "Session close-open sign matches the first bar close-open sign.",
        "reversal_definition": "Session close-open sign is opposite the first bar close-open sign.",
        "directional_efficiency_ratio_definition": "abs(session_close - session_open) / sum(abs(intra-session close-to-close path steps))",
        "close_location_value_definition": "(session_close - session_low) / (session_high - session_low), with zero-range sessions mapped to 0.5",
        "low_sample_threshold": LOW_SAMPLE_THRESHOLD,
        "datasets": dataset_notes,
    }
    (output_dir / "summary_notes.json").write_text(json.dumps(summary_notes, indent=2), encoding="utf-8")

    print(f"Saved session structure diagnostics to {output_dir}")
    print(session_summary_by_pair.to_string(index=False))


if __name__ == "__main__":
    main()
