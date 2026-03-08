from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.dukascopy_downloader import (
    DownloadConfig,
    build_tasks,
    default_manifest_path,
    parse_date_range,
    print_summary,
    run_downloads,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Dukascopy tick files with retries, resume support, and manifest logging"
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--start-date", help="YYYY-MM-DD (UTC)")
    parser.add_argument("--end-date", help="YYYY-MM-DD (UTC, inclusive)")
    parser.add_argument("--output-dir", default="data/raw/dukascopy/EURUSD")
    parser.add_argument("--manifest-file", help="JSONL manifest path")
    parser.add_argument("--resume", action="store_true", help="Skip already valid files")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--max-retries", "--retries", dest="max_retries", type=int, default=4)
    parser.add_argument("--timeout", "--timeout-seconds", dest="timeout", type=float, default=30.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--max-consecutive-failures", type=int, default=25)
    parser.add_argument(
        "--no-validate-lzma",
        action="store_true",
        help="Disable lightweight .bi5 decompression validation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    start_date, end_date = parse_date_range(
        year=args.year,
        start_date_str=args.start_date,
        end_date_str=args.end_date,
    )
    tasks = build_tasks(args.symbol.upper(), start_date, end_date)
    manifest_path = (
        Path(args.manifest_file)
        if args.manifest_file
        else default_manifest_path(output_root, start_date, end_date)
    )

    cfg = DownloadConfig(
        output_root=output_root,
        manifest_path=manifest_path,
        timeout=args.timeout,
        max_retries=args.max_retries,
        sleep_seconds=args.sleep_seconds,
        max_workers=args.max_workers,
        resume=args.resume,
        validate_lzma=not args.no_validate_lzma,
        max_consecutive_failures=args.max_consecutive_failures,
    )

    print(
        f"Starting Dukascopy download for {args.symbol.upper()} "
        f"{start_date.isoformat()} -> {end_date.isoformat()} "
        f"(hours={len(tasks)}, workers={args.max_workers}, resume={args.resume})"
    )
    summary = run_downloads(tasks, cfg)
    print_summary(summary)


if __name__ == "__main__":
    main()
