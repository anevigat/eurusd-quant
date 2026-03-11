from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "scripts" / "update_recent_bars.py"
LIVE_SCRIPT = ROOT / "scripts" / "run_live_signal_engine.py"
SIM_SCRIPT = ROOT / "scripts" / "run_paper_trading_simulator.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full paper trading loop orchestrator")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--days-back", type=int, default=7)
    parser.add_argument("--bars-file", default="data/bars/15m/eurusd_bars_latest.parquet")
    parser.add_argument("--signals-dir", default="signals")
    parser.add_argument("--log-dir", default="paper_trading_log")
    parser.add_argument("--strategy", default="ny_impulse_mean_reversion")
    parser.add_argument("--all-strategies", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--as-of-date", help="Optional YYYY-MM-DD")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_orchestrator_log(log_file: Path, step: str, status: str, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_file.exists()
    with log_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "step", "status", "message"])
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": utc_now_iso(),
                "step": step,
                "status": status,
                "message": message,
            }
        )


def parse_update_message(stdout: str) -> str:
    m = re.search(r"New bars added:\s*(\d+)", stdout)
    if m:
        return f"bars_added={m.group(1)}"
    return "completed"


def parse_live_message(stdout: str) -> str:
    if "no signal" in stdout:
        return "no_signal"
    if "signal" in stdout.lower():
        return "signal_generated"
    return "completed"


def parse_sim_message(stdout: str) -> str:
    if "no trade events" in stdout:
        return "no_trade_events"
    if "Trade closed" in stdout:
        return "trade_closed"
    if "Open trade" in stdout:
        return "trade_opened"
    return "completed"


def run_step_with_parse(step: str, cmd: list[str], log_file: Path, parser_fn) -> None:
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)

    if result.returncode != 0:
        message = stderr.splitlines()[-1] if stderr else f"exit_code={result.returncode}"
        append_orchestrator_log(log_file, step, "failure", message)
        print(f"Paper trading loop failed at step: {step}")
        raise SystemExit(result.returncode)

    append_orchestrator_log(log_file, step, "success", parser_fn(stdout))


def main() -> None:
    args = parse_args()

    log_file = Path(args.log_dir) / "orchestrator_log.csv"
    bars_dir = str(Path(args.bars_file).parent)

    update_cmd = [
        sys.executable,
        str(UPDATE_SCRIPT),
        "--symbol",
        args.symbol,
        "--days-back",
        str(args.days_back),
        "--bars-dir",
        bars_dir,
        "--log-dir",
        args.log_dir,
    ]
    if args.skip_download:
        update_cmd.append("--skip-download")
    if args.as_of_date:
        update_cmd.extend(["--as-of-date", args.as_of_date])

    live_cmd = [
        sys.executable,
        str(LIVE_SCRIPT),
        "--bars-file",
        args.bars_file,
        "--output-dir",
        args.signals_dir,
        "--log-dir",
        args.log_dir,
    ]
    if args.all_strategies:
        live_cmd.append("--all-strategies")
    else:
        live_cmd.extend(["--strategy", args.strategy])

    sim_cmd = [
        sys.executable,
        str(SIM_SCRIPT),
        "--signals-dir",
        args.signals_dir,
        "--bars-file",
        args.bars_file,
        "--log-dir",
        args.log_dir,
    ]

    print("[1/3] Updating recent bars...")
    run_step_with_parse("update_recent_bars", update_cmd, log_file, parse_update_message)

    print("[2/3] Running live signal engine...")
    run_step_with_parse("run_live_signal_engine", live_cmd, log_file, parse_live_message)

    print("[3/3] Running paper trading simulator...")
    run_step_with_parse("run_paper_trading_simulator", sim_cmd, log_file, parse_sim_message)

    print("Paper trading loop completed successfully.")


if __name__ == "__main__":
    main()
