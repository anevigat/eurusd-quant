from __future__ import annotations

from datetime import time

import pandas as pd


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(hour=int(hours), minute=int(minutes))


def in_time_window(
    timestamp: pd.Timestamp,
    start: time,
    end: time,
) -> bool:
    """Check if timestamp is in [start, end) window."""
    current = timestamp.time()
    if start <= end:
        return start <= current < end
    return current >= start or current < end
