from __future__ import annotations


def resolve_exit_reason(stop_hit: bool, tp_hit: bool, mode: str = "conservative") -> str | None:
    if not stop_hit and not tp_hit:
        return None
    if stop_hit and tp_hit:
        if mode != "conservative":
            raise ValueError(f"Unsupported ambiguity mode: {mode}")
        return "stop_loss"
    return "stop_loss" if stop_hit else "take_profit"
