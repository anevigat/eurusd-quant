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
)
from eurusd_quant.analytics.volatility_regimes import (
    assign_time_aware_volatility_regimes,
    compute_session_step_forward_returns,
    summarize_forward_returns_by_regime,
    summarize_regime_descriptives,
    summarize_regime_persistence,
    summarize_regime_transition_matrix,
    summarize_session_behavior_by_regime,
    summarize_session_regime_transitions,
)


PAIR_FILES = {
    "EURUSD": "eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD": "gbpusd_bars_15m_2018_2024.parquet",
    "USDJPY": "usdjpy_bars_15m_2018_2024.parquet",
}
LOW_SAMPLE_THRESHOLD = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze time-aware volatility regimes across FX sessions.")
    parser.add_argument(
        "--bars-root",
        type=Path,
        default=None,
        help="Directory containing 15m pair bar parquet files. Defaults to local data/bars/15m or the sibling main checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/volatility_regimes"),
        help="Directory where volatility regime outputs will be written.",
    )
    parser.add_argument(
        "--lookback-sessions",
        type=int,
        default=120,
        help="Trailing number of prior sessions used to define time-aware regime percentiles per pair.",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=30,
        help="Minimum number of prior sessions required before assigning a non-unknown regime.",
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


def add_low_sample_flag(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "sample_count" in result.columns:
        result["low_sample"] = result["sample_count"] < LOW_SAMPLE_THRESHOLD
    return result


def pooled_regime_summary(frame: pd.DataFrame) -> pd.DataFrame:
    pooled = summarize_regime_descriptives(frame, ["volatility_regime"])
    pooled.insert(0, "pair", "ALL")
    return pooled


def pooled_persistence_summary(frame: pd.DataFrame) -> pd.DataFrame:
    per_pair = summarize_regime_persistence(frame)
    per_pair = per_pair.dropna(subset=["run_count"]).copy()
    pooled_rows = []
    for regime, group in per_pair.groupby("volatility_regime", observed=True):
        total_runs = group["run_count"].sum()
        total_transition_samples = group["transition_sample_count"].fillna(0).sum()
        if total_runs <= 0:
            continue
        pooled_rows.append(
            {
                "pair": "ALL",
                "volatility_regime": regime,
                "run_count": int(total_runs),
                "avg_duration_sessions": float((group["avg_duration_sessions"] * group["run_count"]).sum() / total_runs),
                "median_duration_sessions": float(group["median_duration_sessions"].median()),
                "p90_duration_sessions": float(group["p90_duration_sessions"].median()),
                "max_duration_sessions": int(group["max_duration_sessions"].max()),
                "persistence_probability": float(
                    (group["persistence_probability"] * group["transition_sample_count"]).sum()
                    / total_transition_samples
                )
                if total_transition_samples > 0
                else float("nan"),
                "transition_sample_count": int(total_transition_samples),
                "sample_count": int(total_transition_samples if total_transition_samples > 0 else total_runs),
            }
        )
    return pd.concat([per_pair, pd.DataFrame(pooled_rows)], ignore_index=True).sort_values(
        ["pair", "volatility_regime"]
    )


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
    session_records = assign_time_aware_volatility_regimes(
        session_records,
        metric_col="realized_vol",
        lookback_sessions=args.lookback_sessions,
        min_history=args.min_history,
    )
    session_records = compute_session_step_forward_returns(session_records, horizons=(1, 2, 4, 8))
    known_regimes = session_records.loc[session_records["volatility_regime"] != "unknown"].copy()

    regime_summary_by_pair = add_low_sample_flag(
        pd.concat(
            [
                summarize_regime_descriptives(known_regimes, ["pair", "volatility_regime"]),
                pooled_regime_summary(known_regimes),
            ],
            ignore_index=True,
        ).sort_values(["pair", "volatility_regime"])
    )

    regime_persistence_summary = add_low_sample_flag(pooled_persistence_summary(known_regimes))
    regime_transition_matrix = add_low_sample_flag(summarize_regime_transition_matrix(known_regimes))
    conditional_forward_returns = add_low_sample_flag(
        summarize_forward_returns_by_regime(known_regimes, horizons=(1, 2, 4, 8))
    )

    session_behavior_by_regime = add_low_sample_flag(
        pd.concat(
            [
                summarize_session_behavior_by_regime(known_regimes),
                summarize_session_behavior_by_regime(known_regimes.assign(pair="ALL")),
            ],
            ignore_index=True,
        ).sort_values(["pair", "session", "volatility_regime"])
    )

    session_regime_transition_summary = add_low_sample_flag(
        summarize_session_regime_transitions(known_regimes)
    )

    regime_summary_by_pair.to_csv(output_dir / "regime_summary_by_pair.csv", index=False)
    regime_persistence_summary.to_csv(output_dir / "regime_persistence_summary.csv", index=False)
    regime_transition_matrix.to_csv(output_dir / "regime_transition_matrix.csv", index=False)
    conditional_forward_returns.to_csv(output_dir / "conditional_forward_returns_by_regime.csv", index=False)
    session_behavior_by_regime.to_csv(output_dir / "session_behavior_by_regime.csv", index=False)
    session_regime_transition_summary.to_csv(output_dir / "session_regime_transition_summary.csv", index=False)

    notes = {
        "timeframe": "15m",
        "timestamp_convention": "UTC bar-open timestamps",
        "session_windows_utc": SESSION_WINDOWS_UTC,
        "session_rollover_hour_utc": FX_SESSION_ROLLOVER_HOUR_UTC,
        "regime_metric": "session realized volatility (std of 15m close-to-close returns within each session)",
        "regime_metric_computed_per_pair": True,
        "regime_metric_lookback_sessions": args.lookback_sessions,
        "regime_metric_min_history": args.min_history,
        "regime_quantiles": {"low": 1 / 3, "high": 2 / 3},
        "regime_labels": ["low_vol", "medium_vol", "high_vol"],
        "forward_return_horizons": [1, 2, 4, 8],
        "forward_return_unit": "session steps",
        "low_sample_threshold": LOW_SAMPLE_THRESHOLD,
        "datasets": dataset_notes,
    }
    (output_dir / "volatility_regime_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")

    print(f"Saved volatility regime diagnostics to {output_dir}")
    print(regime_summary_by_pair.to_string(index=False))


if __name__ == "__main__":
    main()
