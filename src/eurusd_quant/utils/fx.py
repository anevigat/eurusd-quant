from __future__ import annotations


def infer_pip_size(symbol: str) -> float:
    pair = str(symbol or "").upper()
    if pair.endswith("JPY"):
        return 0.01
    return 0.0001
