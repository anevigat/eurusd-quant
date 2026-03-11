from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_TRADES = "outputs/ny_impulse_exit_models_extended/atr_1_0/trades.parquet"
DEFAULT_OUTPUT_DIR = "outputs/ny_impulse_montecarlo"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monte Carlo robustness test for NY impulse trades.")
    parser.add_argument("--trades", default=DEFAULT_TRADES, help="Path to trades.parquet")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument(
        "--returns-column",
        default="net_pnl",
        choices=["net_pnl", "pnl_pips"],
        help="Trade return column used to simulate equity curves",
    )
    parser.add_argument(
        "--num-simulations",
        type=int,
        default=1000,
        help="Number of Monte Carlo simulations",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--num-equity-examples",
        type=int,
        default=10,
        help="Number of example equity curves to save",
    )
    return parser.parse_args()


def max_drawdown_from_returns(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    equity = np.cumsum(returns)
    peaks = np.maximum.accumulate(equity)
    drawdowns = equity - peaks
    return float(abs(drawdowns.min()))


def profit_factor_from_returns(returns: np.ndarray) -> float:
    wins = float(returns[returns > 0].sum())
    losses_abs = abs(float(returns[returns < 0].sum()))
    if losses_abs == 0.0:
        return float(np.inf) if wins > 0 else 0.0
    return float(wins / losses_abs)


def main() -> None:
    args = parse_args()

    if args.num_simulations < 1:
        raise ValueError("--num-simulations must be >= 1")
    if args.num_equity_examples < 1:
        raise ValueError("--num-equity-examples must be >= 1")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_parquet(args.trades)
    if trades.empty:
        raise ValueError("Trades file is empty")
    if args.returns_column not in trades.columns:
        raise ValueError(f"Missing returns column '{args.returns_column}'")

    returns = trades[args.returns_column].astype(float).to_numpy()
    n_trades = int(returns.size)

    rng = np.random.default_rng(args.seed)

    summary_rows: list[dict[str, float | int]] = []
    example_curves: list[pd.DataFrame] = []

    examples_to_save = min(args.num_equity_examples, args.num_simulations)

    for sim_id in range(1, args.num_simulations + 1):
        shuffled = returns[rng.permutation(n_trades)]
        equity = np.cumsum(shuffled)

        final_equity = float(equity[-1]) if equity.size else 0.0
        max_dd = max_drawdown_from_returns(shuffled)
        pf = profit_factor_from_returns(shuffled)

        summary_rows.append(
            {
                "simulation": sim_id,
                "final_equity": final_equity,
                "max_drawdown": max_dd,
                "profit_factor": pf,
            }
        )

        if sim_id <= examples_to_save:
            example_curves.append(
                pd.DataFrame(
                    {
                        "simulation": sim_id,
                        "trade_index": np.arange(1, n_trades + 1, dtype=int),
                        "equity": equity,
                    }
                )
            )

    sims_df = pd.DataFrame(summary_rows)

    median_final_equity = float(sims_df["final_equity"].median())
    median_dd = float(sims_df["max_drawdown"].median())
    p95_dd = float(sims_df["max_drawdown"].quantile(0.95))
    worst_dd = float(sims_df["max_drawdown"].max())

    summary = {
        "input_trades": args.trades,
        "returns_column": args.returns_column,
        "num_trades": n_trades,
        "num_simulations": int(args.num_simulations),
        "seed": int(args.seed),
        "median_final_equity": median_final_equity,
        "median_max_drawdown": median_dd,
        "p95_max_drawdown": p95_dd,
        "worst_max_drawdown": worst_dd,
    }

    with (output_dir / "simulation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    drawdown_df = sims_df[["simulation", "max_drawdown", "final_equity", "profit_factor"]].copy()
    drawdown_df.to_csv(output_dir / "drawdown_distribution.csv", index=False)

    if example_curves:
        equity_examples_df = pd.concat(example_curves, ignore_index=True)
    else:
        equity_examples_df = pd.DataFrame(columns=["simulation", "trade_index", "equity"])
    equity_examples_df.to_csv(output_dir / "equity_examples.csv", index=False)

    print(f"median_dd: {median_dd:.6f}")
    print(f"p95_dd: {p95_dd:.6f}")
    print(f"worst_dd: {worst_dd:.6f}")
    print(f"\nSaved summary: {output_dir / 'simulation_summary.json'}")
    print(f"Saved drawdown distribution: {output_dir / 'drawdown_distribution.csv'}")
    print(f"Saved equity examples: {output_dir / 'equity_examples.csv'}")


if __name__ == "__main__":
    main()
