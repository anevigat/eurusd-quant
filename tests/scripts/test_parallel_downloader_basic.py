from __future__ import annotations

import json
import lzma
import threading
import time
from pathlib import Path

from eurusd_quant.data.dukascopy_downloader import (
    DownloadConfig,
    DownloadTask,
    ManifestLogger,
    run_downloads,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _tasks() -> list[DownloadTask]:
    # Monday open-session hours.
    return [
        DownloadTask(symbol="EURUSD", year=2024, month=1, day=8, hour=hour)
        for hour in range(10, 16)
    ]


def _cfg(tmp_path: Path, *, max_workers: int, label: str) -> DownloadConfig:
    return DownloadConfig(
        output_root=tmp_path / label / "raw",
        manifest_path=tmp_path / label / "manifest.jsonl",
        timeout=1.0,
        max_retries=0,
        sleep_seconds=0.0,
        max_workers=max_workers,
        resume=False,
        validate_lzma=True,
        max_consecutive_failures=10,
    )


def test_parallel_downloader_runs_concurrently_and_manifest_append_is_main_thread(
    tmp_path: Path, monkeypatch
) -> None:
    payload = lzma.compress(b"tick-data")

    def opener(_url: str, timeout: float) -> _FakeResponse:  # noqa: ARG001
        time.sleep(0.08)
        return _FakeResponse(payload)

    tasks = _tasks()

    serial_cfg = _cfg(tmp_path, max_workers=1, label="serial")
    start_serial = time.monotonic()
    serial_summary = run_downloads(
        tasks,
        serial_cfg,
        opener=opener,
        sleep_fn=lambda _seconds: None,
        progress_every=1000,
    )
    serial_elapsed = time.monotonic() - start_serial

    append_threads: list[str] = []
    original_append = ManifestLogger.append

    def _append_with_thread_capture(self: ManifestLogger, row: dict[str, object]) -> None:
        append_threads.append(threading.current_thread().name)
        original_append(self, row)

    monkeypatch.setattr(ManifestLogger, "append", _append_with_thread_capture)

    parallel_cfg = _cfg(tmp_path, max_workers=3, label="parallel")
    start_parallel = time.monotonic()
    parallel_summary = run_downloads(
        tasks,
        parallel_cfg,
        opener=opener,
        sleep_fn=lambda _seconds: None,
        progress_every=1000,
    )
    parallel_elapsed = time.monotonic() - start_parallel

    assert serial_summary["successful"] == len(tasks)
    assert parallel_summary["successful"] == len(tasks)
    assert parallel_summary["tasks_submitted"] == len(tasks)
    assert parallel_summary["tasks_completed"] == len(tasks)
    assert parallel_summary["workers_used"] == 3

    # Bounded parallelism should materially improve wall-clock time.
    assert parallel_elapsed < serial_elapsed * 0.8

    assert append_threads
    assert all(name == "MainThread" for name in append_threads)

    lines = parallel_cfg.manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(tasks)
    rows = [json.loads(line) for line in lines]
    assert all(row["status"] == "success" for row in rows)
