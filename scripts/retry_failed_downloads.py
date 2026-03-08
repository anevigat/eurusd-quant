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
    load_failed_tasks_from_manifest,
    print_summary,
    run_downloads,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry only failed Dukascopy downloads listed in a manifest JSONL"
    )
    parser.add_argument("--manifest-file", required=True, help="Existing download manifest JSONL")
    parser.add_argument("--manifest-out", help="Output manifest JSONL (defaults to --manifest-file)")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--output-dir", default="data/raw/dukascopy/EURUSD")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--max-consecutive-failures", type=int, default=25)
    parser.add_argument("--no-validate-lzma", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_in = Path(args.manifest_file)
    manifest_out = Path(args.manifest_out) if args.manifest_out else manifest_in
    tasks = load_failed_tasks_from_manifest(manifest_in, symbol=args.symbol.upper())
    if not tasks:
        print(f"No failed tasks found in {manifest_in}")
        return

    cfg = DownloadConfig(
        output_root=Path(args.output_dir),
        manifest_path=manifest_out,
        timeout=args.timeout,
        max_retries=args.max_retries,
        sleep_seconds=args.sleep_seconds,
        max_workers=args.max_workers,
        resume=args.resume,
        validate_lzma=not args.no_validate_lzma,
        max_consecutive_failures=args.max_consecutive_failures,
    )
    print(
        f"Retrying {len(tasks)} failed tasks for {args.symbol.upper()} "
        f"(workers={args.max_workers}, resume={args.resume})"
    )
    summary = run_downloads(tasks, cfg)
    print_summary(summary)


if __name__ == "__main__":
    main()
