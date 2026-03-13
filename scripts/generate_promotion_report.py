from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a markdown promotion report from walk-forward outputs.")
    parser.add_argument("--input-dir", required=True, help="Walk-forward root or specific config directory")
    parser.add_argument("--output-file", required=True, help="Markdown output path")
    parser.add_argument(
        "--hypothesis",
        default="A fixed strategy configuration can survive standardized OOS walk-forward validation and stressed execution costs.",
        help="Hypothesis text for the report header",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def discover_run_dirs(input_dir: Path) -> list[Path]:
    if (input_dir / "promotion_report.json").exists():
        return [input_dir]
    run_dirs = sorted(path for path in input_dir.iterdir() if path.is_dir() and (path / "promotion_report.json").exists())
    if not run_dirs:
        raise ValueError(f"No promotion_report.json files found under {input_dir}")
    return run_dirs


def format_gate(gate: dict[str, Any]) -> str:
    status = "PASS" if gate["passed"] is True else "FAIL" if gate["passed"] is False else "NOT_EVALUATED"
    return f"| {gate['name']} | {status} | `{gate['actual']}` | `{gate['threshold']}` |"


def build_report_section(run_dir: Path, hypothesis: str) -> str:
    aggregate = load_json(run_dir / "aggregate.json")
    promotion = load_json(run_dir / "promotion_report.json")
    splits_path = run_dir / "splits.csv"
    config_path = run_dir / "config.json"

    yearly_rows = aggregate.get("yearly_metrics", [])
    stress_metrics = aggregate.get("stress_test_metrics", {})
    yearly_table = ["| year | trades | expectancy | PF | net_pnl | max_dd |", "|---|---:|---:|---:|---:|---:|"]
    for row in yearly_rows:
        yearly_table.append(
            f"| {row['year']} | {row['total_trades']} | {row['expectancy']:.6f} | {row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f} |"
        )
    if len(yearly_table) == 2:
        yearly_table.append("| n/a | 0 | 0.000000 | 0.0000 | 0.000000 | 0.000000 |")

    stress_table = ["| scenario | expectancy | PF | net_pnl | max_dd |", "|---|---:|---:|---:|---:|"]
    for scenario_name, scenario_payload in stress_metrics.items():
        metrics = scenario_payload["metrics"]
        stress_table.append(
            f"| {scenario_name} | {metrics['expectancy']:.6f} | {metrics['profit_factor']:.4f} | {metrics['net_pnl']:.6f} | {metrics['max_drawdown']:.6f} |"
        )

    gate_table = ["| gate | status | actual | threshold |", "|---|---|---|---|"]
    for gate in promotion["gates"]:
        gate_table.append(format_gate(gate))

    ranges = promotion.get("is_oos_ranges", [])
    range_lines = [
        f"- split {item['split_id']}: IS {item['train_start']} -> {item['train_end']}, OOS {item['test_start']} -> {item['test_end']}"
        for item in ranges
    ]
    if not range_lines:
        range_lines = ["- No walk-forward ranges recorded"]

    metrics = aggregate["aggregate_oos_metrics"]
    exact_rules = promotion["thresholds"]

    return "\n".join(
        [
            f"## {aggregate['strategy']} / {aggregate['config_hash']}",
            "",
            "### Hypothesis",
            hypothesis,
            "",
            "### Exact Rules",
            f"- thresholds: `{json.dumps(exact_rules, sort_keys=True)}`",
            "",
            "### Data Used",
            f"- bars: `{aggregate['bars']}`",
            f"- config: `{config_path}`",
            f"- split metrics: `{splits_path}`",
            "",
            "### IS/OOS Ranges",
            *range_lines,
            "",
            "### Aggregate OOS Metrics",
            f"- total_trades: {metrics['total_trades']}",
            f"- expectancy: {metrics['expectancy']:.6f}",
            f"- profit_factor: {metrics['profit_factor']:.4f}",
            f"- net_pnl: {metrics['net_pnl']:.6f}",
            f"- max_drawdown: {metrics['max_drawdown']:.6f}",
            "",
            "### Yearly Metrics",
            *yearly_table,
            "",
            "### Stressed-Cost Metrics",
            *stress_table,
            "",
            "### Gate Results",
            *gate_table,
            "",
            "### Decision",
            f"- decision: `{promotion['decision']}`",
            f"- promotion_status: `{promotion['promotion_status']}`",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    sections = [
        "# Strategy Promotion Report",
        "",
        *[build_report_section(run_dir, args.hypothesis) for run_dir in discover_run_dirs(input_dir)],
    ]
    output_file.write_text("\n".join(sections).strip() + "\n", encoding="utf-8")
    print(f"Promotion report written to: {output_file}")


if __name__ == "__main__":
    main()
