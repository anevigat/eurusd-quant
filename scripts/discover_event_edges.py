from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = [
    "event_family",
    "event_name",
    "bucket",
    "direction",
    "sample_size",
    "median_return_4_bars",
    "median_adverse_move_4_bars",
    "edge_score",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank event buckets by edge score and generate candidate strategy edges."
    )
    parser.add_argument(
        "--input",
        default="outputs/event_return_analyzer/event_bucket_summary.csv",
        help="Input event_bucket_summary.csv from analyze_event_returns.py",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/event_edge_discovery",
        help="Directory for top_continuation_edges.csv, top_reversal_edges.csv, edge_candidates.json",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=200,
        help="Minimum sample size required for ranking",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Top buckets to save per category (continuation/reversal)",
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=10,
        help="Number of edge candidates to include in edge_candidates.json",
    )
    return parser.parse_args()


def load_bucket_summary(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "event_family",
        "event_name",
        "bucket",
        "direction",
        "sample_size",
        "median_return_4_bars",
        "median_adverse_move_4_bars",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Input summary missing required columns: {missing}")
    return df


def compute_edge_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out[out["sample_size"] > 0].copy()
    out["edge_score"] = out["median_return_4_bars"].abs() * np.log(out["sample_size"])
    return out


def apply_min_sample_filter(df: pd.DataFrame, min_sample_size: int) -> pd.DataFrame:
    return df[df["sample_size"] >= min_sample_size].copy()


def split_continuation_reversal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    continuation = df[df["median_return_4_bars"] > 0].copy()
    reversal = df[df["median_return_4_bars"] < 0].copy()
    return continuation, reversal


def rank_edges(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    ranked = df.sort_values("edge_score", ascending=False).head(top_n).copy()
    return ranked[OUTPUT_COLUMNS].reset_index(drop=True)


def canonical_family(event_family: str) -> str:
    value = str(event_family).lower()
    if "impulse" in value:
        return "impulse"
    if "compression" in value:
        return "compression"
    if "new_high_low" in value:
        return "new_high_low"
    return value


def infer_suggested_strategy_type(
    event_family: str, median_return_4_bars: float
) -> str:
    fam = canonical_family(event_family)
    if fam == "impulse" and median_return_4_bars < 0:
        return "impulse_fade"
    if fam == "compression" and median_return_4_bars > 0:
        return "volatility_breakout"
    if fam == "new_high_low" and median_return_4_bars < 0:
        return "breakout_failure"
    return "experimental"


def build_edge_candidates(
    continuation_edges: pd.DataFrame,
    reversal_edges: pd.DataFrame,
    candidate_count: int,
) -> list[dict[str, object]]:
    continuation = continuation_edges.copy()
    continuation["edge_type"] = "continuation"
    reversal = reversal_edges.copy()
    reversal["edge_type"] = "reversal"
    combined = pd.concat([continuation, reversal], ignore_index=True)
    combined = combined.sort_values("edge_score", ascending=False).head(candidate_count)

    candidates: list[dict[str, object]] = []
    for _, row in combined.iterrows():
        notes = (
            "High sample and meaningful 4-bar continuation edge"
            if row["edge_type"] == "continuation"
            else "High sample and meaningful 4-bar reversal edge"
        )
        candidates.append(
            {
                "event_family": row["event_family"],
                "event_name": row["event_name"],
                "bucket": row["bucket"],
                "direction": row["direction"],
                "edge_type": row["edge_type"],
                "median_return_4_bars": float(row["median_return_4_bars"]),
                "median_adverse_move_4_bars": float(row["median_adverse_move_4_bars"]),
                "sample_size": int(row["sample_size"]),
                "suggested_strategy_type": infer_suggested_strategy_type(
                    str(row["event_family"]), float(row["median_return_4_bars"])
                ),
                "notes": notes,
            }
        )
    return candidates


def print_console_table(
    continuation_edges: pd.DataFrame, reversal_edges: pd.DataFrame
) -> None:
    cont = continuation_edges.copy()
    cont["edge_type"] = "continuation"
    rev = reversal_edges.copy()
    rev["edge_type"] = "reversal"
    table = pd.concat([rev, cont], ignore_index=True)
    table = table.sort_values("edge_score", ascending=False).head(20)

    printable = table[
        ["edge_type", "event_name", "bucket", "direction", "sample_size", "median_return_4_bars"]
    ].rename(columns={"event_name": "event", "sample_size": "sample"})
    print("\nTop discovered edges:")
    print(printable.to_string(index=False))


def run_discovery(
    input_path: str,
    output_dir: str,
    min_sample_size: int,
    top_n: int,
    candidate_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    bucket_summary = load_bucket_summary(input_path)
    scored = compute_edge_score(bucket_summary)
    filtered = apply_min_sample_filter(scored, min_sample_size=min_sample_size)
    continuation, reversal = split_continuation_reversal(filtered)
    top_continuation = rank_edges(continuation, top_n=top_n)
    top_reversal = rank_edges(reversal, top_n=top_n)
    candidates = build_edge_candidates(
        top_continuation, top_reversal, candidate_count=candidate_count
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    continuation_path = out_dir / "top_continuation_edges.csv"
    reversal_path = out_dir / "top_reversal_edges.csv"
    candidates_path = out_dir / "edge_candidates.json"

    top_continuation.to_csv(continuation_path, index=False)
    top_reversal.to_csv(reversal_path, index=False)
    candidates_path.write_text(
        json.dumps({"candidates": candidates}, indent=2), encoding="utf-8"
    )
    return top_continuation, top_reversal, candidates


def main() -> None:
    args = parse_args()
    continuation, reversal, candidates = run_discovery(
        input_path=args.input,
        output_dir=args.output_dir,
        min_sample_size=args.min_sample_size,
        top_n=args.top_n,
        candidate_count=args.candidate_count,
    )

    print(f"continuation_edges: {len(continuation)}")
    print(f"reversal_edges: {len(reversal)}")
    print(f"candidates: {len(candidates)}")
    print(f"saved: {Path(args.output_dir) / 'top_continuation_edges.csv'}")
    print(f"saved: {Path(args.output_dir) / 'top_reversal_edges.csv'}")
    print(f"saved: {Path(args.output_dir) / 'edge_candidates.json'}")
    print_console_table(continuation, reversal)


if __name__ == "__main__":
    main()
