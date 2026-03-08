from __future__ import annotations

import json
import lzma
import random
import socket
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


BASE_URL = "https://datafeed.dukascopy.com/datafeed"
TRANSIENT_HTTP_CODES = {408, 425, 429}


@dataclass(frozen=True)
class DownloadTask:
    symbol: str
    year: int
    month: int
    day: int
    hour: int

    @property
    def url(self) -> str:
        month_zero_based = self.month - 1
        return (
            f"{BASE_URL}/{self.symbol}/{self.year}/{month_zero_based:02d}/"
            f"{self.day:02d}/{self.hour:02d}h_ticks.bi5"
        )

    @property
    def relative_path(self) -> Path:
        return (
            Path(str(self.year))
            / f"{self.month:02d}"
            / f"{self.day:02d}"
            / f"{self.hour:02d}h_ticks.bi5"
        )

    @property
    def hour_label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d} {self.hour:02d}:00"


@dataclass(frozen=True)
class DownloadResult:
    task: DownloadTask
    target_path: Path
    status: str
    retries: int
    error_message: str | None
    attempted_at: str


@dataclass(frozen=True)
class DownloadConfig:
    output_root: Path
    manifest_path: Path
    timeout: float
    max_retries: int
    sleep_seconds: float
    max_workers: int
    resume: bool
    validate_lzma: bool
    max_consecutive_failures: int
    backoff_base_seconds: float = 0.5
    backoff_jitter_seconds: float = 0.3


class FileValidationError(RuntimeError):
    pass


class ManifestLogger:
    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, row: dict[str, object]) -> None:
        payload = json.dumps(row, separators=(",", ":"), sort_keys=True)
        with self._lock:
            with self.manifest_path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")


class RequestThrottler:
    def __init__(self, sleep_seconds: float) -> None:
        self.sleep_seconds = max(0.0, sleep_seconds)
        self._lock = threading.Lock()
        self._last_request_monotonic: float | None = None

    def wait(self, sleep_fn: Callable[[float], None]) -> None:
        if self.sleep_seconds <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if self._last_request_monotonic is None:
                self._last_request_monotonic = now
                return
            elapsed = now - self._last_request_monotonic
            if elapsed < self.sleep_seconds:
                sleep_fn(self.sleep_seconds - elapsed)
                now = time.monotonic()
            self._last_request_monotonic = now


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def date_label_for_task(task: DownloadTask) -> tuple[int, int, int]:
    return task.year, task.month, task.day


def default_manifest_path(output_root: Path, start_date: date, end_date: date) -> Path:
    if start_date.year == end_date.year:
        year_label = f"{start_date.year}"
    else:
        year_label = f"{start_date.year}_{end_date.year}"
    return output_root.parent / f"download_manifest_{year_label}.jsonl"


def parse_date_range(
    *, year: int | None, start_date_str: str | None, end_date_str: str | None
) -> tuple[date, date]:
    if start_date_str is None and end_date_str is not None:
        raise ValueError("--end-date requires --start-date")

    if start_date_str is not None:
        start_dt = date.fromisoformat(start_date_str)
        end_dt = date.fromisoformat(end_date_str) if end_date_str else start_dt
    else:
        if year is None:
            raise ValueError("Either --year or --start-date must be provided")
        start_dt = date(year, 1, 1)
        end_dt = date(year, 12, 31)

    if end_dt < start_dt:
        raise ValueError("--end-date must be >= --start-date")
    return start_dt, end_dt


def build_tasks(symbol: str, start_date: date, end_date: date) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    current = datetime(
        year=start_date.year,
        month=start_date.month,
        day=start_date.day,
        tzinfo=timezone.utc,
    )
    final = datetime(
        year=end_date.year,
        month=end_date.month,
        day=end_date.day,
        hour=23,
        tzinfo=timezone.utc,
    )
    while current <= final:
        tasks.append(
            DownloadTask(
                symbol=symbol,
                year=current.year,
                month=current.month,
                day=current.day,
                hour=current.hour,
            )
        )
        current += timedelta(hours=1)
    return tasks


def is_valid_download_file(path: Path, validate_lzma: bool) -> tuple[bool, str | None]:
    if not path.exists():
        return False, "file_missing"
    if path.stat().st_size <= 0:
        return False, "file_empty"
    if not validate_lzma:
        return True, None
    try:
        lzma.decompress(path.read_bytes())
    except lzma.LZMAError:
        return False, "lzma_decode_error"
    return True, None


def evaluate_existing_file_for_resume(
    path: Path, *, resume: bool, validate_lzma: bool
) -> tuple[bool, str | None]:
    if not resume:
        return False, None
    valid, reason = is_valid_download_file(path, validate_lzma=validate_lzma)
    if valid:
        return True, None
    return False, reason


def should_retry_exception(exc: Exception, attempt: int, max_retries: int) -> bool:
    if attempt >= max_retries:
        return False

    if isinstance(exc, HTTPError):
        if exc.code in TRANSIENT_HTTP_CODES:
            return True
        if 500 <= exc.code < 600:
            return True
        return False
    if isinstance(exc, (URLError, TimeoutError, socket.timeout, ConnectionResetError)):
        return True
    if isinstance(exc, FileValidationError):
        return True
    return False


def _error_to_message(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTPError {exc.code}: {exc.reason}"
    return f"{type(exc).__name__}: {exc}"


def build_manifest_row(
    *,
    task: DownloadTask,
    target_path: Path,
    status: str,
    retries: int,
    error_message: str | None,
    attempted_at: str,
) -> dict[str, object]:
    year, month, day = date_label_for_task(task)
    return {
        "timestamp": attempted_at,
        "symbol": task.symbol,
        "year": year,
        "month": month,
        "day": day,
        "hour": task.hour,
        "url": task.url,
        "target_path": str(target_path),
        "status": status,
        "retries": retries,
        "error": error_message,
    }


def _download_one(
    task: DownloadTask,
    cfg: DownloadConfig,
    *,
    throttler: RequestThrottler,
    rng: random.Random,
    opener: Callable[..., object] = urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    target_path = cfg.output_root / task.relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    should_skip, invalid_reason = evaluate_existing_file_for_resume(
        target_path,
        resume=cfg.resume,
        validate_lzma=cfg.validate_lzma,
    )
    if should_skip:
        return DownloadResult(
            task=task,
            target_path=target_path,
            status="skipped",
            retries=0,
            error_message=None,
            attempted_at=utc_now_iso(),
        )
    if invalid_reason and target_path.exists():
        target_path.unlink(missing_ok=True)

    for attempt in range(cfg.max_retries + 1):
        try:
            throttler.wait(sleep_fn=sleep_fn)
            with opener(task.url, timeout=cfg.timeout) as response:
                payload = response.read()
            target_path.write_bytes(payload)

            valid, reason = is_valid_download_file(
                target_path, validate_lzma=cfg.validate_lzma
            )
            if not valid:
                target_path.unlink(missing_ok=True)
                raise FileValidationError(reason or "file_validation_failed")

            return DownloadResult(
                task=task,
                target_path=target_path,
                status="success",
                retries=attempt,
                error_message=None,
                attempted_at=utc_now_iso(),
            )
        except Exception as exc:
            if not should_retry_exception(exc, attempt=attempt, max_retries=cfg.max_retries):
                return DownloadResult(
                    task=task,
                    target_path=target_path,
                    status="failed",
                    retries=attempt,
                    error_message=_error_to_message(exc),
                    attempted_at=utc_now_iso(),
                )

            backoff_seconds = cfg.backoff_base_seconds * (2**attempt)
            backoff_seconds += rng.uniform(0.0, cfg.backoff_jitter_seconds)
            sleep_fn(backoff_seconds)

    return DownloadResult(
        task=task,
        target_path=target_path,
        status="failed",
        retries=cfg.max_retries,
        error_message="unexpected_retry_fallthrough",
        attempted_at=utc_now_iso(),
    )


def run_downloads(
    tasks: list[DownloadTask],
    cfg: DownloadConfig,
    *,
    opener: Callable[..., object] = urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    progress_every: int = 500,
    random_seed: int = 42,
) -> dict[str, object]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not tasks:
        return {
            "total_attempted": 0,
            "successful": 0,
            "skipped": 0,
            "failed": 0,
            "total_retries": 0,
            "elapsed_seconds": 0.0,
            "first_requested_hour": None,
            "last_requested_hour": None,
        }

    manifest = ManifestLogger(cfg.manifest_path)
    throttler = RequestThrottler(cfg.sleep_seconds)
    start = time.monotonic()
    counts = {"success": 0, "skipped": 0, "failed": 0}
    total_retries = 0
    consecutive_failures = 0

    def handle_result(idx: int, result: DownloadResult) -> None:
        nonlocal total_retries, consecutive_failures
        counts[result.status] += 1
        total_retries += result.retries
        if result.status == "failed":
            consecutive_failures += 1
            if (
                cfg.max_consecutive_failures > 0
                and consecutive_failures >= cfg.max_consecutive_failures
                and consecutive_failures % cfg.max_consecutive_failures == 0
            ):
                print(
                    "WARNING: many consecutive failures detected "
                    f"({consecutive_failures}). Possible throttling/rate limiting. "
                    "Try lower --max-workers and higher --sleep-seconds."
                )
        else:
            consecutive_failures = 0

        manifest.append(
            build_manifest_row(
                task=result.task,
                target_path=result.target_path,
                status=result.status,
                retries=result.retries,
                error_message=result.error_message,
                attempted_at=result.attempted_at,
            )
        )
        if idx % progress_every == 0 or idx == len(tasks):
            print(
                f"{idx}/{len(tasks)} "
                f"(success={counts['success']}, skipped={counts['skipped']}, failed={counts['failed']}, "
                f"retries={total_retries})"
            )

    if cfg.max_workers <= 1:
        rng = random.Random(random_seed)
        for idx, task in enumerate(tasks, start=1):
            result = _download_one(
                task,
                cfg,
                throttler=throttler,
                rng=rng,
                opener=opener,
                sleep_fn=sleep_fn,
            )
            handle_result(idx, result)
    else:
        with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
            futures = [
                pool.submit(
                    _download_one,
                    task,
                    cfg,
                    throttler=throttler,
                    rng=random.Random(random_seed + idx),
                    opener=opener,
                    sleep_fn=sleep_fn,
                )
                for idx, task in enumerate(tasks, start=1)
            ]
            for idx, future in enumerate(as_completed(futures), start=1):
                handle_result(idx, future.result())

    elapsed = time.monotonic() - start
    summary = {
        "total_attempted": len(tasks),
        "successful": counts["success"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "total_retries": total_retries,
        "elapsed_seconds": round(elapsed, 2),
        "first_requested_hour": tasks[0].hour_label,
        "last_requested_hour": tasks[-1].hour_label,
        "manifest_path": str(cfg.manifest_path),
    }
    return summary


def print_summary(summary: dict[str, object]) -> None:
    print("Download completed")
    print(
        f"total attempted={summary['total_attempted']}, "
        f"successful={summary['successful']}, "
        f"skipped={summary['skipped']}, "
        f"failed={summary['failed']}, "
        f"retries={summary['total_retries']}"
    )
    print(f"elapsed seconds={summary['elapsed_seconds']}")
    print(
        "requested hours: "
        f"{summary['first_requested_hour']} -> {summary['last_requested_hour']}"
    )
    print(f"manifest: {summary['manifest_path']}")


def load_failed_tasks_from_manifest(
    manifest_path: Path, *, symbol: str | None = None
) -> list[DownloadTask]:
    latest_by_key: dict[tuple[str, int, int, int, int], dict[str, object]] = {}
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row_symbol = str(row["symbol"]).upper()
            key = (
                row_symbol,
                int(row["year"]),
                int(row["month"]),
                int(row["day"]),
                int(row["hour"]),
            )
            latest_by_key[key] = row

    failed_tasks: list[DownloadTask] = []
    for key, row in latest_by_key.items():
        row_symbol, year, month, day, hour = key
        if symbol and row_symbol != symbol.upper():
            continue
        if row.get("status") != "failed":
            continue
        failed_tasks.append(
            DownloadTask(
                symbol=row_symbol,
                year=year,
                month=month,
                day=day,
                hour=hour,
            )
        )
    failed_tasks.sort(key=lambda t: (t.year, t.month, t.day, t.hour))
    return failed_tasks
