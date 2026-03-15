#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "research"
FAILURE_OUTPUT_DIR = OUTPUT_ROOT / "failure_statistics"
MATRIX_PATH = DOCS_DIR / "strategy_matrix_status.md"

PAIR_ORDER = ["EURUSD", "GBPUSD", "USDJPY"]
ACTIVE_STATUSES = {
    "candidate",
    "multi_year_validated",
    "walk_forward_validated",
    "cross_pair_validated",
    "paper_trade_candidate",
    "paper_trading",
}
EXPLORATORY_STATUSES = {"idea", "diagnostic", "mvp_tested"}
NUMERIC_RE = r"[+-]?\d+(?:\.\d+)?(?:e-?\d+)?"


@dataclass
class MatrixRow:
    strategy_name: str
    impl: str
    archetype: str
    timeframe: str
    promotion_status: str
    last_evaluation: str
    notes: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy post-mortem research datasets.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
        help="Root directory for generated research outputs.",
    )
    return parser.parse_args()


def git_date_for_first_add(path: Path) -> str | None:
    rel_path = path.relative_to(REPO_ROOT)
    result = subprocess.run(
        [
            "git",
            "log",
            "--diff-filter=A",
            "--format=%ad",
            "--date=short",
            "--",
            str(rel_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


def load_matrix_rows() -> list[MatrixRow]:
    rows: list[MatrixRow] = []
    for line in MATRIX_PATH.read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            continue
        rows.append(
            MatrixRow(
                strategy_name=cells[0].strip("` "),
                impl=cells[1].strip("` "),
                archetype=cells[2].strip(),
                timeframe=cells[3].strip("` "),
                promotion_status=cells[4].strip("` "),
                last_evaluation=cells[5].strip(),
                notes=cells[6].strip(),
            )
        )
    return rows


def strategy_doc_path(strategy_name: str) -> Path | None:
    direct = DOCS_DIR / f"strategy_{strategy_name}.md"
    if direct.exists():
        return direct
    return None


def source_path_for_date(row: MatrixRow) -> Path:
    if row.impl == "code":
        code_path = REPO_ROOT / "src" / "eurusd_quant" / "strategies" / f"{row.strategy_name}.py"
        if code_path.exists():
            return code_path
    doc_path = strategy_doc_path(row.strategy_name)
    if doc_path is not None:
        return doc_path
    return MATRIX_PATH


def status_category(row: MatrixRow) -> str:
    notes = row.notes.lower()
    if row.promotion_status in ACTIVE_STATUSES:
        return "active"
    if row.promotion_status in EXPLORATORY_STATUSES:
        return "exploratory"
    if "freeze" in notes or "frozen" in notes or "historical reference" in notes:
        return "frozen"
    return "rejected"


def inferred_pairs(row: MatrixRow) -> list[str]:
    pairs = re.findall(r"\b(EURUSD|GBPUSD|USDJPY)\b", row.last_evaluation)
    if not pairs:
        pairs = re.findall(r"\b(EURUSD|GBPUSD|USDJPY)\b", row.notes)
    if not pairs:
        doc_path = strategy_doc_path(row.strategy_name)
        if doc_path and doc_path.exists():
            doc_text = doc_path.read_text()
            pairs = re.findall(r"\b(EURUSD|GBPUSD|USDJPY)\b", doc_text)
    if not pairs:
        return ["EURUSD"]
    unique: list[str] = []
    for pair in pairs:
        if pair not in unique and pair in PAIR_ORDER:
            unique.append(pair)
    return unique or ["EURUSD"]


def add_extra_inventory_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    for record in list(rows):
        if record["strategy_name"] == "ny_impulse_mean_reversion" and record["pair"] == "EURUSD":
            extra = dict(record)
            extra["pair"] = "GBPUSD"
            extra["last_evaluation"] = "GBPUSD 15m 2018-2024 cross-pair robustness sweep"
            extra["notes"] = "Cross-pair robustness batch showed GBPUSD below PF 1.0 in both historical and forward ranges."
            rows.append(extra)

    refined_doc = DOCS_DIR / "strategy_london_pullback_continuation_refined.md"
    if refined_doc.exists():
        rows.append(
            {
                "strategy_name": "london_pullback_continuation_refined",
                "archetype": "session breakout continuation",
                "pair": "EURUSD",
                "timeframe": "15m diagnostic",
                "status": "frozen",
                "promotion_status": "diagnostic",
                "impl": "doc",
                "date_added": git_date_for_first_add(refined_doc),
                "date_rejected": None,
                "last_evaluation": "EURUSD 15m 2018-2024 refined continuation diagnostic",
                "notes": "Diagnostic-only refinement of the continuation branch; kept for historical reference after the family was frozen.",
            }
        )
    return rows


def build_inventory(rows: list[MatrixRow]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in rows:
        for pair in inferred_pairs(row):
            source_path = source_path_for_date(row)
            records.append(
                {
                    "strategy_name": row.strategy_name,
                    "archetype": row.archetype,
                    "pair": pair,
                    "timeframe": row.timeframe,
                    "status": status_category(row),
                    "promotion_status": row.promotion_status,
                    "impl": row.impl,
                    "date_added": git_date_for_first_add(source_path),
                    "date_rejected": None,
                    "last_evaluation": row.last_evaluation,
                    "notes": row.notes,
                }
            )
    records = add_extra_inventory_rows(records)
    df = pd.DataFrame(records).drop_duplicates(subset=["strategy_name", "pair"])
    return df.sort_values(["strategy_name", "pair"]).reset_index(drop=True)


def normalize_percent(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 1.0:
        return value / 100.0
    return value


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def first_match(text: str, patterns: Iterable[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return to_float(match.group(1))
    return None


def first_string(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def extract_section(text: str, heading: str) -> str | None:
    level = len(heading) - len(heading.lstrip("#"))
    stop_patterns = [rf"\n{'#' * i} " for i in range(1, level + 1)]
    stop_group = "|".join(stop_patterns + [r"\Z"])
    pattern = rf"{re.escape(heading)}\n(.*?)(?={stop_group})"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1)


def generic_metrics(text: str) -> dict[str, object]:
    trades = first_match(
        text,
        [
            rf"`total_trades`: `({NUMERIC_RE})`",
            rf"`trade_count`: `({NUMERIC_RE})`",
            rf"total_trades: ({NUMERIC_RE})",
            rf"trade_count: ({NUMERIC_RE})",
            rf"`trades`: `({NUMERIC_RE})`",
            rf"trades=`({NUMERIC_RE})`",
            rf"Baseline: `({NUMERIC_RE})` trades",
            rf"total trades: `({NUMERIC_RE})`",
        ],
    )
    win_rate = normalize_percent(
        first_match(
            text,
            [
                rf"`win_rate`: `({NUMERIC_RE})`",
                rf"win rate `({NUMERIC_RE})%`",
                rf"`win_rate`: ({NUMERIC_RE})",
                rf"win_rate: ({NUMERIC_RE})",
                rf"win_rate: ({NUMERIC_RE})",
            ],
        )
    )
    profit_factor = first_match(
        text,
        [
            rf"`profit_factor`: `({NUMERIC_RE})`",
            rf"profit factor `({NUMERIC_RE})`",
            rf"PF=`({NUMERIC_RE})`",
            rf"`PF`: `({NUMERIC_RE})`",
            rf"profit_factor: ({NUMERIC_RE})",
            rf"profit_factor: ({NUMERIC_RE})",
        ],
    )
    net_pnl = first_match(
        text,
        [
            rf"`net_pnl`: `({NUMERIC_RE})`",
            rf"net PnL `({NUMERIC_RE})`",
            rf"net_pnl=`({NUMERIC_RE})`",
            rf"net_pnl: ({NUMERIC_RE})",
            rf"net_pnl: ({NUMERIC_RE})",
            rf"net pnl: ({NUMERIC_RE})",
        ],
    )
    max_drawdown = first_match(
        text,
        [
            rf"`max_drawdown`: `({NUMERIC_RE})`",
            rf"max DD `({NUMERIC_RE})`",
            rf"max_dd=`({NUMERIC_RE})`",
            rf"max_drawdown: ({NUMERIC_RE})",
            rf"max_drawdown: ({NUMERIC_RE})",
            rf"max drawdown: ({NUMERIC_RE})",
        ],
    )
    expectancy = first_match(
        text,
        [
            rf"`expectancy`: `({NUMERIC_RE})`",
            rf"expectancy=`({NUMERIC_RE})`",
            rf"expectancy: ({NUMERIC_RE})",
        ],
    )
    return {
        "trade_count": trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "net_pnl": net_pnl,
        "max_drawdown": max_drawdown,
        "expectancy": expectancy,
    }


def extract_false_breakout_multiyear() -> dict[str, object]:
    text = (DOCS_DIR / "research" / "false_breakout_reversal_multiyear_validation.md").read_text()
    return {
        "metric_source": "docs/research/false_breakout_reversal_multiyear_validation.md",
        "sample_period": "2018-2024",
        "trade_count": first_match(text, [rf"Total trades: `({NUMERIC_RE})`"]),
        "profit_factor": None,
        "net_pnl": first_match(text, [rf"Combined net PnL across 2018-2024: `({NUMERIC_RE})`"]),
        "max_drawdown": 0.028868,
        "expectancy": None,
        "win_rate": None,
        "walk_forward_pf": None,
        "oos_result": None,
        "cross_pair_result": None,
    }


def extract_asian_range_breakout() -> dict[str, object]:
    text = (DOCS_DIR / "strategy_asian_range_breakout.md").read_text()
    baseline = re.search(
        rf"Baseline: `({NUMERIC_RE})` trades, win rate `({NUMERIC_RE})%`, net PnL `({NUMERIC_RE})`, profit factor `({NUMERIC_RE})`",
        text,
    )
    return {
        "metric_source": "docs/strategy_asian_range_breakout.md",
        "sample_period": "2023-01-01 to 2023-06-22",
        "trade_count": float(baseline.group(1)) if baseline else None,
        "profit_factor": float(baseline.group(4)) if baseline else None,
        "net_pnl": float(baseline.group(3)) if baseline else None,
        "max_drawdown": None,
        "expectancy": None,
        "win_rate": normalize_percent(float(baseline.group(2))) if baseline else None,
        "walk_forward_pf": None,
        "oos_result": None,
        "cross_pair_result": None,
    }


def extract_candidate_strengthening_session_breakout() -> dict[str, object]:
    text = (DOCS_DIR / "experiments" / "candidate_strengthening_results.md").read_text()
    section = extract_section(text, "## Track B: `session_breakout` On EURUSD") or text
    refined_match = re.search(
        rf"Best refined config .*?- trades: `({NUMERIC_RE})`\n- PF: `({NUMERIC_RE})`\n- net pnl: `({NUMERIC_RE})`\n- max drawdown: `({NUMERIC_RE})`",
        section,
        flags=re.DOTALL,
    )
    return {
        "metric_source": "docs/experiments/candidate_strengthening_results.md",
        "sample_period": "2018-2024",
        "trade_count": float(refined_match.group(1)) if refined_match else first_match(section, [rf"- trades: `({NUMERIC_RE})`"]),
        "profit_factor": float(refined_match.group(2)) if refined_match else first_match(section, [rf"- PF: `({NUMERIC_RE})`"]),
        "net_pnl": float(refined_match.group(3)) if refined_match else first_match(section, [rf"- net pnl: `({NUMERIC_RE})`"]),
        "max_drawdown": float(refined_match.group(4)) if refined_match else first_match(section, [rf"- max drawdown: `({NUMERIC_RE})`"]),
        "expectancy": None,
        "win_rate": None,
        "walk_forward_pf": float(refined_match.group(2)) if refined_match else first_match(section, [rf"- PF: `({NUMERIC_RE})`"]),
        "oos_result": "fail",
        "cross_pair_result": None,
    }


def extract_candidate_strengthening_tsmom_gbpusd() -> dict[str, object]:
    text = (DOCS_DIR / "experiments" / "candidate_strengthening_results.md").read_text()
    section = extract_section(text, "## Track A: `tsmom_ma_cross` On GBPUSD") or text
    return {
        "metric_source": "docs/experiments/candidate_strengthening_results.md",
        "sample_period": "2018-2024",
        "trade_count": first_match(section, [rf"- trades: `({NUMERIC_RE})`"]),
        "profit_factor": first_match(section, [rf"- profit factor: `({NUMERIC_RE})`"]),
        "net_pnl": first_match(section, [rf"- net pnl: `({NUMERIC_RE})`"]),
        "max_drawdown": first_match(section, [rf"- max drawdown: `({NUMERIC_RE})`"]),
        "expectancy": None,
        "win_rate": None,
        "walk_forward_pf": first_match(section, [rf"- profit factor: `({NUMERIC_RE})`"]),
        "oos_result": "fail",
        "cross_pair_result": "fail",
    }


def extract_tsmom_initial(strategy_name: str, pair: str) -> dict[str, object]:
    text = (DOCS_DIR / "experiments" / "tsmom_initial_results.md").read_text()
    if pair == "EURUSD":
        in_sample_match = re.search(
            rf"### `{re.escape(strategy_name)}`\n\n- best config:.*?- in-sample summary: trades=`({NUMERIC_RE})`, PF=`({NUMERIC_RE})`, net_pnl=`({NUMERIC_RE})`, max_dd=`({NUMERIC_RE})`",
            text,
            flags=re.DOTALL,
        )
        oos_match = re.search(
            rf"## Walk-Forward Summary.*?### `{re.escape(strategy_name)}`\n\n- config hash:.*?- OOS trades=`({NUMERIC_RE})`\n- OOS PF=`({NUMERIC_RE})`\n- OOS net_pnl=`({NUMERIC_RE})`\n- OOS expectancy=`({NUMERIC_RE})`\n- OOS max_dd=`({NUMERIC_RE})`",
            text,
            flags=re.DOTALL,
        )
        return {
            "metric_source": "docs/experiments/tsmom_initial_results.md",
            "sample_period": "2018-2024",
            "trade_count": float(in_sample_match.group(1)) if in_sample_match else None,
            "profit_factor": float(in_sample_match.group(2)) if in_sample_match else None,
            "net_pnl": float(in_sample_match.group(3)) if in_sample_match else None,
            "max_drawdown": float(in_sample_match.group(4)) if in_sample_match else None,
            "expectancy": float(oos_match.group(4)) if oos_match else None,
            "win_rate": None,
            "walk_forward_pf": float(oos_match.group(2)) if oos_match else None,
            "oos_result": "fail",
            "cross_pair_result": None,
        }

    section = re.search(
        rf"## Cross-Pair Spot Check Summary.*?### `{re.escape(strategy_name)}` on GBPUSD\n\n- same EURUSD-selected config\n- OOS trades=`({NUMERIC_RE})`\n- OOS PF=`({NUMERIC_RE})`\n- OOS net_pnl=`({NUMERIC_RE})`\n- OOS max_dd=`({NUMERIC_RE})`",
        text,
        flags=re.DOTALL,
    )
    return {
        "metric_source": "docs/experiments/tsmom_initial_results.md",
        "sample_period": "2018-2024",
        "trade_count": float(section.group(1)) if section else None,
        "profit_factor": float(section.group(2)) if section else None,
        "net_pnl": float(section.group(3)) if section else None,
        "max_drawdown": float(section.group(4)) if section else None,
        "expectancy": None,
        "win_rate": None,
        "walk_forward_pf": float(section.group(2)) if section else None,
        "oos_result": "fail",
        "cross_pair_result": "fail",
    }


def extract_ny_impulse_validation(pair: str) -> dict[str, object]:
    if pair == "GBPUSD":
        text = (DOCS_DIR / "cross_pair_robustness.md").read_text()
        return {
            "metric_source": "docs/cross_pair_robustness.md",
            "sample_period": "2018-2024 historical",
            "trade_count": first_match(text, [rf"GBPUSD_historical`: .*trades `({NUMERIC_RE})`"]),
            "profit_factor": first_match(text, [rf"GBPUSD_historical`: .*PF `({NUMERIC_RE})`"]),
            "net_pnl": None,
            "max_drawdown": None,
            "expectancy": None,
            "win_rate": None,
            "walk_forward_pf": None,
            "oos_result": None,
            "cross_pair_result": "fail",
        }

    text = (DOCS_DIR / "experiments" / "ny_impulse_mean_reversion_validation.md").read_text()
    baseline_match = re.search(
        rf"\| baseline \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \|",
        text,
    )
    threshold_row = re.search(
        rf"\| `22` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \| `({NUMERIC_RE})` \|",
        text,
    )
    trades = float(baseline_match.group(1)) if baseline_match else None
    pf = float(baseline_match.group(2)) if baseline_match else None
    net_pnl = float(baseline_match.group(3)) if baseline_match else None
    max_dd = float(baseline_match.group(4)) if baseline_match else None
    return {
        "metric_source": "docs/experiments/ny_impulse_mean_reversion_validation.md",
        "sample_period": "2018-2024",
        "trade_count": trades,
        "profit_factor": pf,
        "net_pnl": net_pnl,
        "max_drawdown": max_dd,
        "expectancy": None,
        "win_rate": None,
        "walk_forward_pf": float(threshold_row.group(2)) if threshold_row else None,
        "oos_result": "fail",
        "cross_pair_result": "fail",
    }


def extract_london_open_impulse_fade() -> dict[str, object]:
    text = (DOCS_DIR / "strategy_london_impulse_ny_reversal.md").read_text()
    section = extract_section(text, "## London Open Impulse Fade MVP") or text
    metrics = generic_metrics(section)
    return {
        "metric_source": "docs/strategy_london_impulse_ny_reversal.md",
        "sample_period": "2018-2024",
        **metrics,
        "walk_forward_pf": None,
        "oos_result": None,
        "cross_pair_result": None,
    }


def extract_volatility_family_section(strategy_name: str) -> dict[str, object]:
    text = (DOCS_DIR / "strategy_volatility_expansion_after_compression.md").read_text()
    heading_map = {
        "volatility_expansion_after_compression": "## MVP Implementation and Results",
        "compression_breakout": "## Alternative Compression Breakout MVP",
        "compression_breakout_continuation": "## Compression + Breakout Continuation MVP",
    }
    section = extract_section(text, heading_map[strategy_name]) or text
    metrics = generic_metrics(section)
    return {
        "metric_source": "docs/strategy_volatility_expansion_after_compression.md",
        "sample_period": "2018-2024",
        **metrics,
        "walk_forward_pf": None,
        "oos_result": None,
        "cross_pair_result": None,
    }


def extract_generic_strategy_doc(strategy_name: str) -> dict[str, object]:
    doc_path = strategy_doc_path(strategy_name)
    if doc_path is None or not doc_path.exists():
        return {
            "metric_source": None,
            "sample_period": None,
            "trade_count": None,
            "profit_factor": None,
            "net_pnl": None,
            "max_drawdown": None,
            "expectancy": None,
            "win_rate": None,
            "walk_forward_pf": None,
            "oos_result": None,
            "cross_pair_result": None,
        }
    text = doc_path.read_text()
    metrics = generic_metrics(text)
    sample_period = first_string(
        text,
        [
            r"Period analyzed: `([^`]+ to [^`]+)`",
            r"Backtest range used for core validation:\n\n- ([^\n]+)",
            r"combined ([0-9]{4}-[0-9]{4}) dataset",
            r"(2018-2024)",
            r"(2023-01-01` to `2023-06-22)",
        ],
    )
    return {
        "metric_source": str(doc_path.relative_to(REPO_ROOT)),
        "sample_period": sample_period,
        **metrics,
        "walk_forward_pf": None,
        "oos_result": None,
        "cross_pair_result": None,
    }


def latest_metrics(strategy_name: str, pair: str) -> dict[str, object]:
    if strategy_name == "asian_range_breakout":
        return extract_asian_range_breakout()
    if strategy_name == "false_breakout_reversal" and pair == "EURUSD":
        return extract_false_breakout_multiyear()
    if strategy_name == "session_breakout" and pair == "EURUSD":
        return extract_candidate_strengthening_session_breakout()
    if strategy_name == "ny_impulse_mean_reversion":
        return extract_ny_impulse_validation(pair)
    if strategy_name == "tsmom_ma_cross" and pair == "GBPUSD":
        return extract_candidate_strengthening_tsmom_gbpusd()
    if strategy_name in {"tsmom_ma_cross", "tsmom_donchian", "tsmom_return_sign"}:
        return extract_tsmom_initial(strategy_name, pair)
    if strategy_name == "london_open_impulse_fade":
        return extract_london_open_impulse_fade()
    if strategy_name in {
        "volatility_expansion_after_compression",
        "compression_breakout",
        "compression_breakout_continuation",
    }:
        return extract_volatility_family_section(strategy_name)
    return extract_generic_strategy_doc(strategy_name)


def failure_modes(row: pd.Series) -> list[str]:
    notes = " ".join(
        filter(
            None,
            [
                str(row.get("notes") or ""),
                str(row.get("last_evaluation") or ""),
                str(row.get("metric_source") or ""),
            ],
        )
    ).lower()
    modes: list[str] = []
    trade_count = row.get("trade_count")
    profit_factor = row.get("profit_factor")
    walk_forward_pf = row.get("walk_forward_pf")

    if any(term in notes for term in ["stress", "spread", "slippage", "cost", "under costs"]):
        if (profit_factor is not None and profit_factor < 1.0) or "does not hold" in notes or "below pf `1.0`" in notes:
            modes.append("spread_sensitive")
    if any(term in notes for term in ["regime dependence", "regime-dependent", "regime dependency", "regime-thin"]):
        modes.append("regime_dependency")
    if any(term in notes for term in ["year concentration", "yearly concentration", "dominant year", "concentration gates"]):
        modes.append("yearly_concentration")
    if any(term in notes for term in ["narrow neighborhood", "parameter neighborhood", "threshold neighborhood", "single threshold"]):
        modes.append("parameter_instability")
        modes.append("overfit_parameter")
    if row.get("cross_pair_result") == "fail" or "pair-specific" in notes or "not purely eurusd-specific" in notes:
        modes.append("portfolio_redundant")
    if row.get("archetype") == "session breakout continuation" or "false breaks" in notes:
        modes.append("false_breakout_noise")
    if trade_count is not None and trade_count < 100:
        modes.append("too_few_trades")
    if walk_forward_pf is not None and walk_forward_pf < 1.0:
        modes.append("no_edge_after_costs")
    elif profit_factor is not None and profit_factor < 1.0:
        modes.append("no_edge_after_costs")

    deduped = []
    for mode in modes:
        if mode not in deduped:
            deduped.append(mode)
    return deduped


def build_performance_dataset(inventory_df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in inventory_df.to_dict(orient="records"):
        metrics = latest_metrics(row["strategy_name"], row["pair"])
        combined = {**row, **metrics}
        combined["failure_modes"] = ",".join(failure_modes(pd.Series(combined)))
        combined["sample_period"] = combined.get("sample_period") or row["last_evaluation"]
        records.append(combined)
    df = pd.DataFrame(records)
    cols = [
        "pair",
        "strategy_name",
        "archetype",
        "timeframe",
        "status",
        "promotion_status",
        "date_added",
        "date_rejected",
        "trade_count",
        "profit_factor",
        "net_pnl",
        "max_drawdown",
        "expectancy",
        "win_rate",
        "sample_period",
        "walk_forward_pf",
        "oos_result",
        "cross_pair_result",
        "failure_modes",
        "metric_source",
        "last_evaluation",
        "notes",
    ]
    return df[cols].sort_values(["strategy_name", "pair"]).reset_index(drop=True)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def summarize_failures(perf_df: pd.DataFrame, output_root: Path) -> None:
    failure_dir = output_root / "failure_statistics"
    failure_dir.mkdir(parents=True, exist_ok=True)

    by_archetype = (
        perf_df.groupby("archetype", dropna=False)
        .agg(
            strategy_count=("strategy_name", "count"),
            rejected_or_frozen=("status", lambda s: int(sum(value in {"rejected", "frozen"} for value in s))),
            avg_profit_factor=("profit_factor", "mean"),
            avg_trade_count=("trade_count", "mean"),
        )
        .reset_index()
        .sort_values("strategy_count", ascending=False)
    )
    write_csv(by_archetype, failure_dir / "failure_by_archetype.csv")

    by_pair = (
        perf_df.groupby("pair", dropna=False)
        .agg(
            strategy_count=("strategy_name", "count"),
            rejected_or_frozen=("status", lambda s: int(sum(value in {"rejected", "frozen"} for value in s))),
            avg_profit_factor=("profit_factor", "mean"),
            avg_trade_count=("trade_count", "mean"),
        )
        .reset_index()
        .sort_values("pair")
    )
    write_csv(by_pair, failure_dir / "failure_by_pair.csv")

    mode_counter: Counter[str] = Counter()
    for value in perf_df["failure_modes"].dropna():
        for mode in [token.strip() for token in str(value).split(",") if token.strip()]:
            mode_counter[mode] += 1
    mode_rows = [{"failure_mode": mode, "count": count} for mode, count in mode_counter.most_common()]
    write_csv(pd.DataFrame(mode_rows), failure_dir / "failure_by_mode.csv")


def build_cross_pair_comparison(perf_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for archetype, group in perf_df.groupby("archetype", dropna=False):
        row: dict[str, object] = {"archetype": archetype}
        for pair in PAIR_ORDER:
            pair_group = group[group["pair"] == pair]
            row[f"{pair.lower()}_avg_pf"] = pair_group["profit_factor"].mean() if not pair_group.empty else None
            row[f"{pair.lower()}_avg_trade_count"] = pair_group["trade_count"].mean() if not pair_group.empty else None
            row[f"{pair.lower()}_avg_max_drawdown"] = pair_group["max_drawdown"].mean() if not pair_group.empty else None
            if pair_group.empty:
                row[f"{pair.lower()}_cost_sensitive_share"] = None
            else:
                row[f"{pair.lower()}_cost_sensitive_share"] = (
                    pair_group["failure_modes"].fillna("").str.contains("spread_sensitive").mean()
                )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("archetype").reset_index(drop=True)


def main() -> None:
    args = parse_args()
    output_root: Path = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    matrix_rows = load_matrix_rows()
    inventory_df = build_inventory(matrix_rows)
    performance_df = build_performance_dataset(inventory_df)

    write_csv(inventory_df, output_root / "strategy_inventory.csv")
    write_csv(performance_df, output_root / "strategy_performance_dataset.csv")
    summarize_failures(performance_df, output_root)
    cross_pair_df = build_cross_pair_comparison(performance_df)
    write_csv(cross_pair_df, output_root / "cross_pair_comparison.csv")


if __name__ == "__main__":
    main()
