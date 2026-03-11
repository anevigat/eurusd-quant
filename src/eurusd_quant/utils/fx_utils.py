from __future__ import annotations


def normalize_symbol(symbol: str) -> str:
    """Return normalized uppercase FX symbol (for example EURUSD, USDJPY)."""
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())


def infer_pip_size(symbol: str) -> float:
    """Infer pip size for spot FX symbols."""
    normalized = normalize_symbol(symbol)
    if normalized.endswith("JPY"):
        return 0.01
    return 0.0001


def pips_to_price(symbol: str, pips: float) -> float:
    """Convert pip distance to price distance for symbol."""
    return float(pips) * infer_pip_size(symbol)


def price_to_pips(symbol: str, price_delta: float) -> float:
    """Convert price distance to pip distance for symbol."""
    return float(price_delta) / infer_pip_size(symbol)
