from __future__ import annotations

from datetime import time

import pandas as pd

from eurusd_quant.data.sessions import in_time_window


def test_time_window_is_start_inclusive_end_exclusive() -> None:
    start = time(7, 0)
    end = time(10, 0)
    assert in_time_window(pd.Timestamp("2024-01-02 07:00:00", tz="UTC"), start, end)
    assert in_time_window(pd.Timestamp("2024-01-02 09:59:00", tz="UTC"), start, end)
    assert not in_time_window(pd.Timestamp("2024-01-02 10:00:00", tz="UTC"), start, end)
