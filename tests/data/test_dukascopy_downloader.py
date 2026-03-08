from __future__ import annotations

import json
import lzma
from pathlib import Path
from urllib.error import HTTPError, URLError

from eurusd_quant.data.dukascopy_downloader import (
    DownloadTask,
    FileValidationError,
    build_manifest_row,
    evaluate_existing_file_for_resume,
    is_valid_download_file,
    load_failed_tasks_from_manifest,
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
