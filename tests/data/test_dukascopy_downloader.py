from __future__ import annotations

import json
import lzma
from pathlib import Path
from urllib.error import HTTPError, URLError

from eurusd_quant.data.dukascopy_downloader import (
    DownloadConfig,
    DownloadTask,
    FileValidationError,
    build_manifest_row,
    evaluate_existing_file_for_resume,
    is_valid_download_file,
    is_expected_no_data_hour,
    load_failed_tasks_from_manifest,
    run_downloads,
    should_retry_exception,
)


def test_build_manifest_row_contains_required_fields() -> None:
    task = DownloadTask(symbol="EURUSD", year=2023, month=1, day=2, hour=3)
    row = build_manifest_row(
        task=task,
        target_path=Path("data/raw/dukascopy/EURUSD/2023/01/02/03h_ticks.bi5"),
        status="failed",
        retries=2,
        error_message="HTTPError 429: Too Many Requests",
        attempted_at="2026-03-08T15:00:00+00:00",
    )
    assert row["symbol"] == "EURUSD"
    assert row["year"] == 2023
    assert row["month"] == 1
    assert row["day"] == 2
    assert row["hour"] == 3
    assert row["status"] == "failed"
    assert row["retries"] == 2
    assert row["error"] is not None
    assert row["target_path"].endswith("03h_ticks.bi5")


def test_is_valid_download_file_checks_existence_size_and_lzma(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.bi5"
    valid, reason = is_valid_download_file(missing_path, validate_lzma=True)
    assert valid is False
    assert reason == "file_missing"

    empty_path = tmp_path / "empty.bi5"
    empty_path.write_bytes(b"")
    valid, reason = is_valid_download_file(empty_path, validate_lzma=True)
    assert valid is False
    assert reason == "file_empty"

    valid_path = tmp_path / "valid.bi5"
    valid_path.write_bytes(lzma.compress(b"tick-data"))
    valid, reason = is_valid_download_file(valid_path, validate_lzma=True)
    assert valid is True
    assert reason is None

    bad_path = tmp_path / "bad.bi5"
    bad_path.write_bytes(b"not-lzma")
    valid, reason = is_valid_download_file(bad_path, validate_lzma=True)
    assert valid is False
    assert reason == "lzma_decode_error"


def test_evaluate_existing_file_for_resume_logic(tmp_path: Path) -> None:
    file_path = tmp_path / "hour.bi5"
    file_path.write_bytes(lzma.compress(b"ok"))

    should_skip, reason = evaluate_existing_file_for_resume(
        file_path, resume=True, validate_lzma=True
    )
    assert should_skip is True
    assert reason is None

    should_skip, reason = evaluate_existing_file_for_resume(
        file_path, resume=False, validate_lzma=True
    )
    assert should_skip is False
    assert reason is None

    file_path.write_bytes(b"corrupt")
    should_skip, reason = evaluate_existing_file_for_resume(
        file_path, resume=True, validate_lzma=True
    )
    assert should_skip is False
    assert reason == "lzma_decode_error"


def test_should_retry_exception() -> None:
    assert (
        should_retry_exception(
            HTTPError(url="u", code=429, msg="Too Many Requests", hdrs=None, fp=None),
            attempt=0,
            max_retries=3,
        )
        is True
    )
    assert (
        should_retry_exception(
            HTTPError(url="u", code=404, msg="Not Found", hdrs=None, fp=None),
            attempt=0,
            max_retries=3,
        )
        is False
    )
    assert should_retry_exception(URLError("temporary"), attempt=1, max_retries=3) is True
    assert should_retry_exception(TimeoutError("timeout"), attempt=1, max_retries=3) is True
    assert (
        should_retry_exception(FileValidationError("bad file"), attempt=1, max_retries=3) is True
    )
    assert should_retry_exception(URLError("temporary"), attempt=3, max_retries=3) is False


def test_load_failed_tasks_from_manifest_uses_latest_status(tmp_path: Path) -> None:
    manifest = tmp_path / "download_manifest_2023.jsonl"
    rows = [
        {
            "timestamp": "2026-03-08T12:00:00+00:00",
            "symbol": "EURUSD",
            "year": 2023,
            "month": 1,
            "day": 1,
            "hour": 0,
            "status": "failed",
        },
        {
            "timestamp": "2026-03-08T12:01:00+00:00",
            "symbol": "EURUSD",
            "year": 2023,
            "month": 1,
            "day": 1,
            "hour": 0,
            "status": "success",
        },
        {
            "timestamp": "2026-03-08T12:02:00+00:00",
            "symbol": "EURUSD",
            "year": 2023,
            "month": 1,
            "day": 1,
            "hour": 1,
            "status": "failed",
        },
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    tasks = load_failed_tasks_from_manifest(manifest, symbol="EURUSD")
    assert len(tasks) == 1
    assert tasks[0].hour == 1


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_weekend_empty_download_is_classified_no_data_without_retries(tmp_path: Path) -> None:
    calls = {"count": 0}

    def opener(_url: str, timeout: float) -> _FakeResponse:  # noqa: ARG001
        calls["count"] += 1
        return _FakeResponse(b"")

    task = DownloadTask(symbol="EURUSD", year=2023, month=1, day=7, hour=10)  # Saturday
    cfg = DownloadConfig(
        output_root=tmp_path / "raw",
        manifest_path=tmp_path / "manifest.jsonl",
        timeout=1.0,
        max_retries=5,
        sleep_seconds=0.0,
        max_workers=1,
        resume=False,
        validate_lzma=True,
        max_consecutive_failures=10,
    )
    summary = run_downloads(
        [task],
        cfg,
        opener=opener,
        sleep_fn=lambda _seconds: None,
        progress_every=1,
    )
    assert calls["count"] == 1
    assert summary["skipped_no_data"] == 1
    assert summary["failed"] == 0
    rows = [json.loads(line) for line in cfg.manifest_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["status"] == "skipped_no_data"
    assert rows[-1]["retries"] == 0


def test_true_network_failure_still_retries(tmp_path: Path) -> None:
    calls = {"count": 0}

    def opener(_url: str, timeout: float) -> _FakeResponse:  # noqa: ARG001
        calls["count"] += 1
        raise URLError("temporary DNS failure")

    task = DownloadTask(symbol="EURUSD", year=2023, month=1, day=2, hour=10)  # Monday
    cfg = DownloadConfig(
        output_root=tmp_path / "raw",
        manifest_path=tmp_path / "manifest.jsonl",
        timeout=1.0,
        max_retries=2,
        sleep_seconds=0.0,
        max_workers=1,
        resume=False,
        validate_lzma=True,
        max_consecutive_failures=10,
    )
    summary = run_downloads(
        [task],
        cfg,
        opener=opener,
        sleep_fn=lambda _seconds: None,
        progress_every=1,
    )
    assert calls["count"] == 3
    assert summary["failed"] == 1
    assert summary["total_retries"] == 2
    rows = [json.loads(line) for line in cfg.manifest_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["status"] == "failed"
    assert rows[-1]["retries"] == 2


def test_is_expected_no_data_hour_weekend_boundaries() -> None:
    assert is_expected_no_data_hour(
        DownloadTask(symbol="EURUSD", year=2023, month=1, day=6, hour=21)
    ) is False
    assert is_expected_no_data_hour(
        DownloadTask(symbol="EURUSD", year=2023, month=1, day=6, hour=22)
    ) is False
    assert is_expected_no_data_hour(
        DownloadTask(symbol="EURUSD", year=2023, month=1, day=6, hour=23)
    ) is True
    assert is_expected_no_data_hour(
        DownloadTask(symbol="EURUSD", year=2023, month=1, day=8, hour=21)
    ) is True
    assert is_expected_no_data_hour(
        DownloadTask(symbol="EURUSD", year=2023, month=1, day=8, hour=22)
    ) is False
