from __future__ import annotations

import pandas as pd

from eurusd_quant.validation.promotion import PromotionThresholds
from eurusd_quant.validation.walk_forward import generate_walk_forward_splits, run_walk_forward_validation


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2018-01-01", "2024-12-31", freq="D", tz="UTC")
    size = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "bid_open": [1.1000] * size,
            "ask_open": [1.1002] * size,
            "bid_high": [1.1005] * size,
            "ask_high": [1.1007] * size,
            "bid_low": [1.0995] * size,
            "ask_low": [1.0997] * size,
            "bid_close": [1.1001] * size,
            "ask_close": [1.1003] * size,
            "spread_open": [0.0002] * size,
            "spread_high": [0.0002] * size,
            "spread_low": [0.0002] * size,
            "spread_close": [0.0002] * size,
        }
    )


def _fake_runner(
    bars: pd.DataFrame,
    strategy_name: str,
    strategy_config: dict,
    execution_config: dict,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()

    years = sorted({pd.Timestamp(ts).year for ts in bars["timestamp"]})
    rows = []
    for year in years:
        entry_time = pd.Timestamp(f"{year}-01-15 00:00:00", tz="UTC")
        rows.append(
            {
                "symbol": "EURUSD",
                "side": "long",
                "signal_time": entry_time,
                "entry_time": entry_time,
                "exit_time": entry_time + pd.Timedelta(hours=1),
                "entry_price": 1.1000,
                "exit_price": 1.1003,
                "stop_loss": 1.0990,
                "take_profit": 1.1010,
                "exit_reason": "time_exit",
                "bars_held": 1,
                "gross_pnl": 1.0,
                "fee": float(execution_config["fee_per_trade"]),
                "net_pnl": 1.0 - float(execution_config["fee_per_trade"]),
                "pnl_pips": (1.0 - float(execution_config["fee_per_trade"])) / 0.0001,
                "slippage_cost": float(execution_config["market_slippage_pips"]) * 0.01,
                "spread_cost": 0.0,
            }
        )
    return pd.DataFrame(rows)


def test_generate_walk_forward_splits_rolls_by_test_window() -> None:
    splits = generate_walk_forward_splits(_bars(), train_years=3, test_months=6, embargo_days=0)

    assert len(splits) == 7
    assert splits[0].train_start == pd.Timestamp("2018-01-01 00:00:00+0000", tz="UTC")
    assert splits[0].train_end == pd.Timestamp("2021-01-01 00:00:00+0000", tz="UTC")
    assert splits[1].train_start == pd.Timestamp("2018-07-01 00:00:00+0000", tz="UTC")
    assert splits[-1].test_end == pd.Timestamp("2024-07-01 00:00:00+0000", tz="UTC")


def test_run_walk_forward_validation_aggregates_oos_only() -> None:
    result = run_walk_forward_validation(
        bars=_bars(),
        strategy_name="session_breakout",
        strategy_config={},
        execution_config={"market_slippage_pips": 0.1, "stop_slippage_pips": 0.2, "fee_per_trade": 0.0},
        train_years=3,
        test_months=12,
        thresholds=PromotionThresholds(
            min_total_trades=1,
            min_trades_per_year=1,
            min_oos_profit_factor=1.0,
            max_oos_drawdown=5.0,
            max_single_year_pnl_share=1.0,
            min_stress_profit_factor=0.5,
            min_stress_expectancy=-1.0,
        ),
        runner=_fake_runner,
    )

    assert len(result.splits) == 3
    assert result.aggregate_metrics["total_trades"] == 3
    assert list(result.yearly_metrics["year"]) == [2021, 2022, 2023]
    assert result.promotion_report["decision"] == "continue"
    assert set(result.stress_results) == {"baseline", "stressed", "harsh"}


def test_run_walk_forward_validation_supports_embargo_days() -> None:
    result = run_walk_forward_validation(
        bars=_bars(),
        strategy_name="session_breakout",
        strategy_config={},
        execution_config={"market_slippage_pips": 0.1, "stop_slippage_pips": 0.2, "fee_per_trade": 0.0},
        train_years=3,
        test_months=12,
        embargo_days=5,
        thresholds=PromotionThresholds(
            min_total_trades=1,
            min_trades_per_year=1,
            min_oos_profit_factor=1.0,
            max_oos_drawdown=5.0,
            max_single_year_pnl_share=1.0,
            min_stress_profit_factor=0.5,
            min_stress_expectancy=-1.0,
        ),
        runner=_fake_runner,
    )

    assert result.splits[0].test_start == pd.Timestamp("2021-01-06 00:00:00+0000", tz="UTC")
