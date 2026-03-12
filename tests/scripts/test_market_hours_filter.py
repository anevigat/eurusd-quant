from __future__ import annotations

from datetime import datetime, timezone

from eurusd_quant.data.dukascopy_downloader import build_tasks, is_fx_market_open


def _ts(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_fx_market_hours_filter_boundaries() -> None:
    # Friday
    assert is_fx_market_open(_ts(2024, 1, 5, 21)) is True
    assert is_fx_market_open(_ts(2024, 1, 5, 23)) is False

    # Saturday
    assert is_fx_market_open(_ts(2024, 1, 6, 12)) is False

    # Sunday
    assert is_fx_market_open(_ts(2024, 1, 7, 20)) is False
    assert is_fx_market_open(_ts(2024, 1, 7, 22)) is True

    # Monday
    assert is_fx_market_open(_ts(2024, 1, 8, 10)) is True


def test_build_tasks_filters_market_closed_hours() -> None:
    tasks = build_tasks(
        symbol="EURUSD",
        start_date=_ts(2024, 1, 5, 21).date(),  # Friday
        end_date=_ts(2024, 1, 7, 23).date(),    # Sunday
    )
    hours = {(t.year, t.month, t.day, t.hour) for t in tasks}

    assert (2024, 1, 5, 21) in hours
    assert (2024, 1, 5, 22) in hours
    assert (2024, 1, 5, 23) not in hours
    assert (2024, 1, 6, 12) not in hours
    assert (2024, 1, 7, 20) not in hours
    assert (2024, 1, 7, 22) in hours
