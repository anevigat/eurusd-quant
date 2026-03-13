from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_INPUT_ROOT = "outputs/event_combination_analysis_v2"
DEFAULT_OUTPUT_DIR = "outputs/event_combination_analysis_v2/cross_pair"

EXPECTED_LABELS = [
    "EURUSD_historical",
    "GBPUSD_historical",
    "EURUSD_forward",
    "GBPUSD_forward",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-pair aggregation for event-combination v2 edges.")
    parser.add_argument("--input-root", default=DEFAULT_INPUT_ROOT, help="Root with per-dataset v2 outputs")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for cross-pair outputs")
    return parser.parse_args()


def parse_dataset_label(label: str) -> tuple[str, str]:
    pair, range_label = label.split("_", 1)
    return pair, range_label


def load_top_edges(input_root: Path) -> tuple[pd.DataFrame, list[str]]:
    rows: list[pd.DataFrame] = []
    missing: list[str] = []
    for label in EXPECTED_LABELS:
        top_path = input_root / label / "top_combination_edges_v2.csv"
        if not top_path.exists():
            missing.append(label)
            continue
        df = pd.read_csv(top_path)
        if df.empty:
            continue
        pair, dataset_range = parse_dataset_label(label)
        df["dataset_label"] = label
        df["pair"] = pair
        df["dataset_range"] = dataset_range
        rows.append(df)
    if not rows:
        return pd.DataFrame(), missing
    combined = pd.concat(rows, ignore_index=True)
    return combined, missing


def build_cross_pair_top_edges(top_edges: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "combination_name",
        "pair",
        "dataset_range",
        "sample_size",
        "median_return_4_bars",
        "median_adverse_move_4_bars",
        "edge_score",
    ]
    out = top_edges[cols].copy()
    out = out.sort_values(["edge_score", "sample_size"], ascending=False).reset_index(drop=True)
    return out


def build_edge_matrix(top_edges: pd.DataFrame) -> pd.DataFrame:
    by_combo_dataset = (
        top_edges.groupby(["combination_name", "dataset_label"], as_index=False)
        .agg(median_return_4_bars=("median_return_4_bars", "median"))
    )
    matrix = by_combo_dataset.pivot(index="combination_name", columns="dataset_label", values="median_return_4_bars")
    matrix = matrix.reindex(columns=[c for c in EXPECTED_LABELS if c in matrix.columns])
    matrix = matrix.reset_index().sort_values("combination_name")
    matrix.columns.name = None
    return matrix


def build_summary(top_edges: pd.DataFrame, edge_matrix: pd.DataFrame, missing_labels: list[str]) -> dict[str, Any]:
    if top_edges.empty:
        return {
            "detected_datasets": [],
            "missing_datasets": missing_labels,
            "note": "No top_combination_edges_v2.csv files found",
        }

    combo_presence = (
        top_edges.groupby("combination_name")
        .agg(
            pairs_supported=("pair", "nunique"),
            ranges_supported=("dataset_range", "nunique"),
            mean_median_return_4_bars=("median_return_4_bars", "mean"),
            total_samples=("sample_size", "sum"),
        )
        .reset_index()
        .sort_values(["pairs_supported", "ranges_supported", "mean_median_return_4_bars"], ascending=[False, False, False])
    )

    shared_pairs = combo_presence[combo_presence["pairs_supported"] >= 2].copy()
    survives_both_ranges = combo_presence[combo_presence["ranges_supported"] >= 2].copy()
    shared_hist_forward = combo_presence[
        (combo_presence["pairs_supported"] >= 2) & (combo_presence["ranges_supported"] >= 2)
    ].copy()

    return {
        "detected_datasets": sorted(top_edges["dataset_label"].unique().tolist()),
        "missing_datasets": missing_labels,
        "total_top_edge_rows": int(len(top_edges)),
        "unique_combinations": int(top_edges["combination_name"].nunique()),
        "shared_across_pairs_count": int(len(shared_pairs)),
        "shared_across_hist_forward_count": int(len(survives_both_ranges)),
        "shared_pairs_and_ranges_count": int(len(shared_hist_forward)),
        "top_shared_across_pairs": shared_pairs.head(15).to_dict(orient="records"),
        "top_shared_across_pairs_and_ranges": shared_hist_forward.head(15).to_dict(orient="records"),
        "matrix_rows": int(len(edge_matrix)),
    }


def run_cross_pair_analysis(input_root: Path, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    top_edges, missing = load_top_edges(input_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    if top_edges.empty:
        summary = {
            "detected_datasets": [],
            "missing_datasets": missing,
            "note": "No top_combination_edges_v2.csv files found",
        }
        (output_dir / "cross_pair_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        pd.DataFrame().to_csv(output_dir / "cross_pair_top_edges.csv", index=False)
        pd.DataFrame().to_csv(output_dir / "cross_pair_edge_matrix.csv", index=False)
        return pd.DataFrame(), pd.DataFrame(), summary

    cross_pair_top = build_cross_pair_top_edges(top_edges)
    edge_matrix = build_edge_matrix(top_edges)
    summary = build_summary(top_edges, edge_matrix, missing)

    cross_pair_top.to_csv(output_dir / "cross_pair_top_edges.csv", index=False)
    edge_matrix.to_csv(output_dir / "cross_pair_edge_matrix.csv", index=False)
    (output_dir / "cross_pair_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return cross_pair_top, edge_matrix, summary


def main() -> None:
    args = parse_args()
    input_root = Path(args.input_root)
    output_dir = Path(args.output_dir)

    top_edges, _, summary = run_cross_pair_analysis(input_root=input_root, output_dir=output_dir)

    if top_edges.empty:
        print("No per-dataset top edge files found.")
        print(f"Saved summary: {output_dir / 'cross_pair_summary.json'}")
        return

    print("Top cross-pair edges:")
    shared = (
        top_edges.groupby("combination_name", as_index=False)
        .agg(
            pairs_supported=("pair", "nunique"),
            median_return_4_bars=("median_return_4_bars", "median"),
        )
        .sort_values(["pairs_supported", "median_return_4_bars"], ascending=[False, False])
    )
    print(shared.head(15).to_string(index=False))
    print(f"\nSaved cross-pair outputs to: {output_dir}")
    print(f"Detected datasets: {', '.join(summary.get('detected_datasets', []))}")


if __name__ == "__main__":
    main()
