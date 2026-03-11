from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class LiveStrategy(ABC):
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier used by the live engine."""

    @abstractmethod
    def evaluate_latest(self, bars: pd.DataFrame) -> dict | None:
        """Return a signal dict for the latest bar, or None if no signal."""
