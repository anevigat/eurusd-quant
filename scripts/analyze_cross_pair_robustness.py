from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_INPUT_ROOT = "outputs/cross_pair_sweeps"
DEFAULT_OUTPUT_DIR = "outputs/cross_pair_robustness"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate cross-pair NY impulse sweep outputs into robustness rankings.")
    parser.add_argument("--input-root", default=DEFAULT_INPUT_ROOT, help="Root containing <pair>/<range>/experiment_results.csv")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory to write robustness outputs")
    parser.add_argument("--min-historical-trades", type=int, default=100, help="Historical trade floor for robust pass checks")
    parser.add_argument("--forward-pf-floor", type=float, default=0.95, help="Forward PF floor for non-catastrophic checks")
    parser.add_argument("--min-pairs-supported", type=int, default=2, help="Minimum pair coverage for robust config list")
    return parser.parse_args()


def discover_experiment_files(input_root: Path) -> list[Path]:
    files = sorted(input_root.glob("*/*/experiment_results.csv"))
    return [path for path in files if path.is_file()]


def load_sweep_results(input_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for csv_path in discover_experiment_files(input_root):
        pair = csv_path.parent.parent.name.upper()
        range_label = csv_path.parent.name
        df = pd.read_csv(csv_path)
        if df.empty:
            continue
        df["pair"] = pair
        df["range_label"] = range_label
        df["pair_range"] = pair + "_" + range_label
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_results = pd.concat(frames, ignore_index=True)
    return all_results


def build_pair_best_configs(all_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for (pair, range_label), group in all_results.groupby(["pair", "range_label"], sort=True):
        if group["ranking_score"].notna().any():
            best = group.loc[group["ranking_score"].idxmax()]
        else:
            best = group.loc[group["score_raw"].idxmax()]
        row = pd.Series(
            {
                "pair": pair,
                "range_label": range_label,
                "best_config_id": best["config_id"],
                "profit_factor": float(best["profit_factor"]),
                "total_trades": int(best["total_trades"]),
                "net_pnl": float(best["net_pnl"]),
                "win_rate": float(best["win_rate"]),
                "max_drawdown": float(best["max_drawdown"]),
                "ranking_score": float(best["ranking_score"]) if pd.notna(best["ranking_score"]) else np.nan,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["pair", "range_label"]).reset_index(drop=True)


def compute_config_ranking(
    all_results: pd.DataFrame,
    *,
    min_historical_trades: int,
    forward_pf_floor: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for config_id, group in all_results.groupby("config_id", sort=True):
        historical = group[group["range_label"] == "historical"]
        forward = group[group["range_label"] == "forward"]

        historical_count = int(len(historical))
        forward_count = int(len(forward))

        hist_pass_count = int(
            ((historical["profit_factor"] > 1.0) & (historical["total_trades"] >= min_historical_trades)).sum()
        )
        fwd_noncat_count = int((forward["profit_factor"] >= forward_pf_floor).sum())

        hist_ratio = float(hist_pass_count / historical_count) if historical_count > 0 else 0.0
        fwd_ratio = float(fwd_noncat_count / forward_count) if forward_count > 0 else 0.5

        # 0.25..1.0 scale, rewarding configs that stay non-catastrophic forward.
        survival_factor = float((0.5 + 0.5 * hist_ratio) * (0.5 + 0.5 * fwd_ratio))
        finite_pf = group["profit_factor"].replace([np.inf, -np.inf], np.nan)
        mean_pf = float(finite_pf.mean()) if finite_pf.notna().any() else 0.0
        mean_pf_for_score = max(0.0, min(mean_pf, 3.0))
        total_trades = int(group["total_trades"].sum())
        robustness_score = float(mean_pf_for_score * math.log(total_trades + 1) * survival_factor)

        rows.append(
            {
                "config_id": config_id,
                "pairs_supported": int(group["pair"].nunique()),
                "datasets_count": int(len(group)),
                "ranges_supported": int(group["range_label"].nunique()),
                "historical_count": historical_count,
                "forward_count": forward_count,
                "historical_pass_count": hist_pass_count,
                "forward_noncat_count": fwd_noncat_count,
                "historical_pass_ratio": hist_ratio,
                "forward_noncat_ratio": fwd_ratio if forward_count > 0 else np.nan,
                "mean_profit_factor": mean_pf,
                "mean_win_rate": float(group["win_rate"].mean()),
                "mean_net_pnl": float(group["net_pnl"].mean()),
                "total_trades_across_pairs": total_trades,
                "survival_factor": survival_factor,
                "robustness_score": robustness_score,
            }
        )

    ranking = pd.DataFrame(rows).sort_values("robustness_score", ascending=False).reset_index(drop=True)
    return ranking


def select_robust_configs(
    global_ranking: pd.DataFrame,
    *,
    min_pairs_supported: int,
) -> pd.DataFrame:
    robust = global_ranking[
        (global_ranking["pairs_supported"] >= min_pairs_supported)
        & (global_ranking["mean_profit_factor"] >= 1.0)
        & (global_ranking["historical_pass_ratio"] >= 0.5)
        & (
            global_ranking["forward_noncat_ratio"].isna()
            | (global_ranking["forward_noncat_ratio"] >= 0.5)
        )
    ].copy()
    return robust.sort_values("robustness_score", ascending=False).reset_index(drop=True)


def build_pf_matrix(all_results: pd.DataFrame) -> pd.DataFrame:
    matrix = all_results.pivot_table(
        index="config_id",
        columns="pair_range",
        values="profit_factor",
        aggfunc="first",
    )
    matrix = matrix.reset_index().sort_values("config_id")
    matrix.columns.name = None
    return matrix


def build_summary(
    *,
    input_root: Path,
    output_dir: Path,
    all_results: pd.DataFrame,
    pair_best_configs: pd.DataFrame,
    global_ranking: pd.DataFrame,
    robust_configs: pd.DataFrame,
    min_historical_trades: int,
    forward_pf_floor: float,
    min_pairs_supported: int,
) -> dict[str, Any]:
    range_best: dict[str, Any] = {}
    for range_label in sorted(all_results["range_label"].unique().tolist()):
        subset = all_results[all_results["range_label"] == range_label]
        if subset.empty:
            continue
        if subset["ranking_score"].notna().any():
            best = subset.loc[subset["ranking_score"].idxmax()]
        else:
            best = subset.loc[subset["score_raw"].idxmax()]
        range_best[range_label] = {
            "config_id": str(best["config_id"]),
            "profit_factor": float(best["profit_factor"]),
            "total_trades": int(best["total_trades"]),
            "pair": str(best["pair"]),
        }

    top_rows = global_ranking.head(10).to_dict(orient="records")

    sweep_summary_path = input_root / "summary.json"
    sweep_metadata: dict[str, Any] | None = None
    if sweep_summary_path.exists():
        sweep_metadata = json.loads(sweep_summary_path.read_text(encoding="utf-8"))

    return {
        "input_root": str(input_root),
        "output_dir": str(output_dir),
        "datasets_analyzed": int(all_results["pair_range"].nunique()),
        "pairs_analyzed": sorted(all_results["pair"].unique().tolist()),
        "ranges_analyzed": sorted(all_results["range_label"].unique().tolist()),
        "configs_analyzed": int(all_results["config_id"].nunique()),
        "robustness_rules": {
            "historical_profit_factor_floor": 1.0,
            "historical_min_trades": min_historical_trades,
            "forward_profit_factor_floor": forward_pf_floor,
            "min_pairs_supported": min_pairs_supported,
            "score_formula": "mean_profit_factor_across_pairs * log(total_trades_across_pairs + 1) * survival_factor",
            "survival_factor": "(0.5 + 0.5*historical_pass_ratio) * (0.5 + 0.5*forward_noncat_ratio)",
        },
        "range_best_configs": range_best,
        "pair_range_best_count": int(len(pair_best_configs)),
        "robust_config_count": int(len(robust_configs)),
        "top_global_configs": top_rows,
        "sweep_metadata": sweep_metadata,
    }


def main() -> None:
    args = parse_args()
    input_root = Path(args.input_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = load_sweep_results(input_root)
    if all_results.empty:
        summary = {
            "input_root": str(input_root),
            "output_dir": str(output_dir),
            "note": "No sweep results found. Run scripts/run_cross_pair_sweeps.py first.",
        }
        with (output_dir / "robustness_summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print("No sweep results found.")
        return

    pair_best_configs = build_pair_best_configs(all_results)
    global_ranking = compute_config_ranking(
        all_results,
        min_historical_trades=int(args.min_historical_trades),
        forward_pf_floor=float(args.forward_pf_floor),
    )
    robust_configs = select_robust_configs(
        global_ranking,
        min_pairs_supported=int(args.min_pairs_supported),
    )
    pf_matrix = build_pf_matrix(all_results)

    pair_best_configs.to_csv(output_dir / "pair_best_configs.csv", index=False)
    global_ranking.to_csv(output_dir / "global_config_ranking.csv", index=False)
    robust_configs.to_csv(output_dir / "robust_configs.csv", index=False)
    pf_matrix.to_csv(output_dir / "config_pair_pf_matrix.csv", index=False)

    summary = build_summary(
        input_root=input_root,
        output_dir=output_dir,
        all_results=all_results,
        pair_best_configs=pair_best_configs,
        global_ranking=global_ranking,
        robust_configs=robust_configs,
        min_historical_trades=int(args.min_historical_trades),
        forward_pf_floor=float(args.forward_pf_floor),
        min_pairs_supported=int(args.min_pairs_supported),
    )
    with (output_dir / "robustness_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("pair | range | best_config | PF | trades | net_pnl")
    for _, row in pair_best_configs.iterrows():
        print(
            f"{row['pair']:>6} | {row['range_label']:>10} | {row['best_config_id']} | "
            f"{row['profit_factor']:.4f} | {int(row['total_trades']):>6} | {row['net_pnl']:.6f}"
        )

    print("\nTop globally robust configs:")
    print("config_id | robustness_score | pairs_supported | mean_pf")
    for _, row in global_ranking.head(10).iterrows():
        print(
            f"{row['config_id']} | {row['robustness_score']:.4f} | "
            f"{int(row['pairs_supported'])} | {row['mean_profit_factor']:.4f}"
        )

    print(f"\nSaved robustness outputs to: {output_dir}")


if __name__ == "__main__":
    main()
