from __future__ import annotations

import argparse
import calendar
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


BASE_URL = "https://datafeed.dukascopy.com/datafeed"


@dataclass(frozen=True)
class DownloadTask:
    year: int
    month: int
    day: int
    hour: int

    @property
    def url(self) -> str:
        month_zero_based = self.month - 1
        return (
            f"{BASE_URL}/EURUSD/{self.year}/{month_zero_based:02d}/"
            f"{self.day:02d}/{self.hour:02d}h_ticks.bi5"
        )

    @property
    def relative_path(self) -> Path:
        return Path(str(self.year)) / f"{self.month:02d}" / f"{self.day:02d}" / f"{self.hour:02d}h_ticks.bi5"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Dukascopy EURUSD tick files for 2023")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--output-dir", default="data/raw/dukascopy/EURUSD")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def build_tasks(year: int) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    for month in range(1, 13):
        _, days_in_month = calendar.monthrange(year, month)
        for day in range(1, days_in_month + 1):
            for hour in range(24):
                tasks.append(DownloadTask(year=year, month=month, day=day, hour=hour))
    return tasks


def download_one(task: DownloadTask, output_root: Path, timeout_seconds: int, retries: int) -> tuple[str, DownloadTask]:
    target = output_root / task.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.stat().st_size > 0:
        return ("skipped", task)

    for attempt in range(retries + 1):
        try:
            with urlopen(task.url, timeout=timeout_seconds) as response:
                payload = response.read()
            target.write_bytes(payload)
            return ("downloaded", task)
        except HTTPError as exc:
            if exc.code == 404:
                return ("missing", task)
            if attempt == retries:
                return ("error", task)
        except URLError:
            if attempt == retries:
                return ("error", task)
        time.sleep(0.25 * (attempt + 1))

    return ("error", task)


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    tasks = build_tasks(args.year)

    counts = {"downloaded": 0, "skipped": 0, "missing": 0, "error": 0}
    failed_urls: list[str] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [pool.submit(download_one, t, output_root, args.timeout_seconds, args.retries) for t in tasks]
        for idx, future in enumerate(as_completed(futures), start=1):
            status, task = future.result()
            counts[status] += 1
            if idx % 500 == 0 or idx == len(tasks):
                print(
                    f"{idx}/{len(tasks)} "
                    f"(downloaded={counts['downloaded']}, skipped={counts['skipped']}, "
                    f"missing={counts['missing']}, error={counts['error']})"
                )
            if status == "error":
                failed_urls.append(task.url)

    print("Download completed")
    print(counts)
    if failed_urls:
        print("Sample failed URLs:")
        for url in failed_urls[:20]:
            print(url)


if __name__ == "__main__":
    main()
