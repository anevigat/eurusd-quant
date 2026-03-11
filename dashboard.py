from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
PAPER_ROOT = ROOT / "paper_trading"
SIGNALS_DIR = PAPER_ROOT / "signals"
STATE_DIR = PAPER_ROOT / "state"
LOGS_DIR = PAPER_ROOT / "logs"

OPEN_POSITIONS_PATH = STATE_DIR / "open_positions.csv"
CLOSED_POSITIONS_PATH = STATE_DIR / "closed_positions.csv"
EQUITY_CURVE_PATH = STATE_DIR / "equity_curve.csv"
ORCHESTRATOR_LOG_PATH = LOGS_DIR / "orchestrator_log.csv"
DATA_UPDATE_LOG_PATH = LOGS_DIR / "data_update_log.csv"
EXECUTION_LOG_PATH = LOGS_DIR / "execution_log.csv"


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_recent_signals(signals_dir: Path, limit: int = 10) -> pd.DataFrame:
    if not signals_dir.exists():
        return pd.DataFrame()

    files = sorted(signals_dir.glob("*.json"))[-limit:]
    rows: list[dict] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "file": path.name,
                "timestamp": payload.get("timestamp"),
                "strategy": payload.get("strategy"),
                "symbol": payload.get("symbol"),
                "side": payload.get("side"),
                "entry_price": payload.get("entry_price"),
                "stop_price": payload.get("stop_price"),
                "target_price": payload.get("target_price"),
                "signal": payload.get("signal", "trade"),
            }
        )
    return pd.DataFrame(rows).sort_values("file", ascending=False).reset_index(drop=True)


def infer_strategy_and_symbol(
    open_positions: pd.DataFrame,
    closed_positions: pd.DataFrame,
    recent_signals: pd.DataFrame,
) -> tuple[str, str]:
    if not open_positions.empty:
        strategy = str(open_positions.iloc[-1].get("strategy", "unknown"))
        symbol = str(open_positions.iloc[-1].get("symbol", "unknown"))
        return strategy, symbol
    if not closed_positions.empty:
        strategy = str(closed_positions.iloc[-1].get("strategy", "unknown"))
        symbol = str(closed_positions.iloc[-1].get("symbol", "unknown"))
        return strategy, symbol
    if not recent_signals.empty:
        non_none = recent_signals[recent_signals["signal"] != "none"]
        source = non_none if not non_none.empty else recent_signals
        strategy = str(source.iloc[0].get("strategy", "unknown"))
        symbol = str(source.iloc[0].get("symbol", "unknown"))
        return strategy, symbol
    return "unknown", "unknown"


def compute_current_drawdown(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty or "equity" not in equity_curve.columns:
        return 0.0
    equity = pd.to_numeric(equity_curve["equity"], errors="coerce").dropna()
    if equity.empty:
        return 0.0
    current = float(equity.iloc[-1])
    peak = float(equity.cummax().iloc[-1])
    return peak - current


def format_last_value(df: pd.DataFrame, column: str, fallback: str = "N/A") -> str:
    if df.empty or column not in df.columns:
        return fallback
    value = df[column].iloc[-1]
    return str(value) if pd.notna(value) else fallback


def main() -> None:
    st.set_page_config(page_title="Paper Trading Dashboard", layout="wide")
    st.title("Paper Trading Dashboard")

    open_positions = read_csv_safe(OPEN_POSITIONS_PATH)
    closed_positions = read_csv_safe(CLOSED_POSITIONS_PATH)
    equity_curve = read_csv_safe(EQUITY_CURVE_PATH)
    orchestrator_log = read_csv_safe(ORCHESTRATOR_LOG_PATH)
    data_update_log = read_csv_safe(DATA_UPDATE_LOG_PATH)
    execution_log = read_csv_safe(EXECUTION_LOG_PATH)
    recent_signals = load_recent_signals(SIGNALS_DIR, limit=10)

    strategy_name, symbol = infer_strategy_and_symbol(
        open_positions=open_positions,
        closed_positions=closed_positions,
        recent_signals=recent_signals,
    )
    last_pipeline_run = format_last_value(orchestrator_log, "timestamp")
    last_data_update = format_last_value(data_update_log, "timestamp")

    st.header("1. Strategy Status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last Pipeline Run", last_pipeline_run)
    c2.metric("Last Data Update", last_data_update)
    c3.metric("Strategy", strategy_name)
    c4.metric("Symbol", symbol)

    st.header("2. Equity Curve")
    total_trades = int(len(closed_positions))
    net_pnl = (
        float(pd.to_numeric(closed_positions.get("pnl", pd.Series(dtype=float)), errors="coerce").sum())
        if not closed_positions.empty
        else 0.0
    )
    win_rate = (
        float((pd.to_numeric(closed_positions["pnl"], errors="coerce") > 0).mean())
        if not closed_positions.empty and "pnl" in closed_positions.columns
        else 0.0
    )
    current_drawdown = compute_current_drawdown(equity_curve)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Trades", f"{total_trades}")
    m2.metric("Win Rate", f"{win_rate:.2%}")
    m3.metric("Net PnL", f"{net_pnl:.6f}")
    m4.metric("Current Drawdown", f"{current_drawdown:.6f}")

    if not equity_curve.empty and {"timestamp", "equity"}.issubset(equity_curve.columns):
        equity_plot = equity_curve.copy()
        equity_plot["timestamp"] = pd.to_datetime(equity_plot["timestamp"], errors="coerce")
        equity_plot["equity"] = pd.to_numeric(equity_plot["equity"], errors="coerce")
        equity_plot = equity_plot.dropna(subset=["timestamp", "equity"]).set_index("timestamp")
        st.line_chart(equity_plot["equity"])
    else:
        st.info("No equity curve data found.")

    st.header("3. Open Positions")
    if open_positions.empty:
        st.info("No open positions.")
    else:
        st.dataframe(open_positions, use_container_width=True, hide_index=True)

    st.header("4. Recent Signals")
    if recent_signals.empty:
        st.info("No signal files found.")
    else:
        st.dataframe(recent_signals, use_container_width=True, hide_index=True)

    st.header("5. Trade History")
    if closed_positions.empty:
        st.info("No closed positions yet.")
    else:
        st.dataframe(
            closed_positions.tail(20).iloc[::-1],
            use_container_width=True,
            hide_index=True,
        )

    st.header("6. System Logs")
    l1, l2 = st.columns(2)
    with l1:
        st.subheader("Orchestrator Log (last 20)")
        if orchestrator_log.empty:
            st.info("No orchestrator log found.")
        else:
            st.dataframe(orchestrator_log.tail(20).iloc[::-1], use_container_width=True, hide_index=True)
    with l2:
        st.subheader("Execution Log (last 20)")
        if execution_log.empty:
            st.info("No execution log found.")
        else:
            st.dataframe(execution_log.tail(20).iloc[::-1], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
