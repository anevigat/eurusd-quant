from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_SCRIPT = ROOT / "scripts" / "download_dukascopy_ticks.py"
CLEAN_SCRIPT = ROOT / "scripts" / "clean_ticks.py"
BUILD_BARS_SCRIPT = ROOT / "scripts" / "build_bars.py"
ADD_SESSIONS_SCRIPT = ROOT / "scripts" / "add_sessions.py"
LAYOUT_DIRS = ("signals", "state", "logs", "reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update recent EURUSD bars for live signal engine")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--days-back", type=int, default=7)
    parser.add_argument("--raw-dir", default="data/raw/dukascopy/EURUSD")
    parser.add_argument("--clean-dir", default="data/cleaned_ticks/EURUSD")
    parser.add_argument("--bars-dir", default="data/bars/15m")
    parser.add_argument("--log-dir", default="paper_trading/logs")
    parser.add_argument(
        "--as-of-date",
        help="Optional YYYY-MM-DD override for update end date (UTC). Defaults to today UTC.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloader step and use existing raw files",
    )
    return parser.parse_args()


def run_command(cmd: list[str]) -> None:
    result = subprocess.run(cmd, check=False, cwd=ROOT)
    if result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"Command failed ({result.returncode}): {joined}")


def infer_layout_root(log_dir: Path) -> Path:
    if log_dir.name in LAYOUT_DIRS:
        return log_dir.parent
    return Path("paper_trading")


def ensure_paper_trading_layout(root: Path) -> None:
    for name in LAYOUT_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def resolve_date_range(days_back: int, as_of_date: str | None) -> tuple[date, date]:
    if days_back < 1:
        raise ValueError("--days-back must be >= 1")

    if as_of_date is None:
        end = datetime.now(timezone.utc).date()
    else:
        end = datetime.strptime(as_of_date, "%Y-%m-%d").date()
    start = end - timedelta(days=days_back - 1)
    return start, end


def clean_recent_ticks(
    symbol: str,
    raw_dir: Path,
    clean_dir: Path,
    start_date: date,
    end_date: date,
) -> Path:
    clean_dir.mkdir(parents=True, exist_ok=True)
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts_exclusive = pd.Timestamp(end_date + timedelta(days=1), tz="UTC")

    staging_root = clean_dir / "_recent_raw_stage"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    current_day = start_date
    while current_day <= end_date:
        src_day_dir = raw_dir / f"{current_day.year}" / f"{current_day.month:02d}" / f"{current_day.day:02d}"
        if src_day_dir.exists():
            dst_day_dir = (
                staging_root
                / f"{current_day.year}"
                / f"{current_day.month:02d}"
                / f"{current_day.day:02d}"
            )
            dst_day_dir.mkdir(parents=True, exist_ok=True)
            for bi5_file in src_day_dir.glob("*h_ticks.bi5"):
                shutil.copy2(bi5_file, dst_day_dir / bi5_file.name)
                copied_files += 1
        current_day += timedelta(days=1)

    if copied_files == 0:
        raise RuntimeError("No raw .bi5 files found for requested date range")

    output_file = clean_dir / f"{symbol.lower()}_ticks_recent.parquet"
    run_command(
        [
            sys.executable,
            str(CLEAN_SCRIPT),
            "--input-dir",
            str(staging_root),
            "--output-file",
            str(output_file),
        ]
    )

    recent_ticks = pd.read_parquet(output_file)
    recent_ticks["timestamp"] = pd.to_datetime(recent_ticks["timestamp"], utc=True)
    recent_ticks = recent_ticks[
        (recent_ticks["timestamp"] >= start_ts) & (recent_ticks["timestamp"] < end_ts_exclusive)
    ]
    recent_ticks = (
        recent_ticks.drop_duplicates(subset=["timestamp", "bid", "ask"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    recent_ticks.to_parquet(output_file, index=False)

    shutil.rmtree(staging_root, ignore_errors=True)
    return output_file


def rebuild_recent_bars(clean_ticks_file: Path, bars_dir: Path, symbol: str) -> Path:
    bars_dir.mkdir(parents=True, exist_ok=True)
    recent_raw_file = bars_dir / f"{symbol.lower()}_bars_15m_recent_raw.parquet"
    recent_final_file = bars_dir / f"{symbol.lower()}_bars_15m_recent.parquet"
    report_file = bars_dir / f"{symbol.lower()}_bars_15m_recent_report.json"

    run_command(
        [
            sys.executable,
            str(BUILD_BARS_SCRIPT),
            "--input-file",
            str(clean_ticks_file),
            "--output-file",
            str(recent_raw_file),
        ]
    )

    run_command(
        [
            sys.executable,
            str(ADD_SESSIONS_SCRIPT),
            "--input-file",
            str(recent_raw_file),
            "--output-file",
            str(recent_final_file),
            "--report-file",
            str(report_file),
        ]
    )

    return recent_final_file


def merge_latest_bars(recent_bars_file: Path, bars_dir: Path) -> tuple[Path, int]:
    latest_file = bars_dir / "eurusd_bars_latest.parquet"

    recent = pd.read_parquet(recent_bars_file)
    recent["timestamp"] = pd.to_datetime(recent["timestamp"], utc=True)

    if latest_file.exists():
        existing = pd.read_parquet(latest_file)
        existing["timestamp"] = pd.to_datetime(existing["timestamp"], utc=True)
    else:
        existing = pd.DataFrame(columns=recent.columns)

    existing_ts = set(existing["timestamp"]) if not existing.empty else set()
    recent_ts = set(recent["timestamp"]) if not recent.empty else set()
    bars_added = len(recent_ts - existing_ts)

    merged = (
        pd.concat([existing, recent], ignore_index=True)
        .sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )

    merged.to_parquet(latest_file, index=False)
    return latest_file, bars_added


def append_update_log(log_dir: Path, bars_added: int, start_date: date, end_date: date) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "data_update_log.csv"
    write_header = not log_file.exists()

    with log_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "bars_added", "start_date", "end_date"],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bars_added": int(bars_added),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )


def main() -> None:
    args = parse_args()

    symbol = args.symbol.upper()
    if symbol != "EURUSD":
        raise ValueError("MVP pipeline supports only EURUSD")

    start_date, end_date = resolve_date_range(args.days_back, args.as_of_date)

    raw_dir = Path(args.raw_dir)
    clean_dir = Path(args.clean_dir)
    bars_dir = Path(args.bars_dir)
    log_dir = Path(args.log_dir)
    ensure_paper_trading_layout(infer_layout_root(log_dir))

    if not args.skip_download:
        print(f"Downloading recent {symbol} ticks (last {args.days_back} days)")
        run_command(
            [
                sys.executable,
                str(DOWNLOAD_SCRIPT),
                "--symbol",
                symbol,
                "--start-date",
                start_date.isoformat(),
                "--end-date",
                end_date.isoformat(),
                "--output-dir",
                str(raw_dir),
                "--resume",
            ]
        )
    else:
        print("Skipping download step")

    print("Cleaning ticks")
    recent_ticks = clean_recent_ticks(
        symbol=symbol,
        raw_dir=raw_dir,
        clean_dir=clean_dir,
        start_date=start_date,
        end_date=end_date,
    )

    print("Building 15m bars")
    recent_bars = rebuild_recent_bars(clean_ticks_file=recent_ticks, bars_dir=bars_dir, symbol=symbol)

    updated_bars_file, bars_added = merge_latest_bars(recent_bars_file=recent_bars, bars_dir=bars_dir)
    append_update_log(log_dir=log_dir, bars_added=bars_added, start_date=start_date, end_date=end_date)

    print(f"Updated bars dataset: {updated_bars_file.name}")
    print(f"New bars added: {bars_added}")


if __name__ == "__main__":
    main()
