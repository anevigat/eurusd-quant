from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class PortfolioMemberConfig:
    name: str
    strategy: str
    pair: str
    timeframe: str
    artifact_path: str
    archetype: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioExperimentConfig:
    name: str
    member_names: tuple[str, ...]
    weighting_method: str = "equal_weight"
    max_weight_per_strategy: float = 1.0
    rebalance_frequency: str = "monthly"
    lookback_days: int = 63
    max_weight_per_pair: float | None = None
    max_usd_direction_exposure: float | None = None
    max_active_strategies_per_pair: int | None = None
    one_strategy_per_pair: bool = False
    blocked_strategy_pairs: tuple[tuple[str, str], ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class StrategyStream:
    config: PortfolioMemberConfig
    trades: pd.DataFrame
    daily_pnl: pd.Series
    active_positions: pd.DataFrame

    @property
    def name(self) -> str:
        return self.config.name


def _normalize_trades(trades: pd.DataFrame, config: PortfolioMemberConfig) -> pd.DataFrame:
    if trades.empty:
        columns = [
            "symbol",
            "side",
            "signal_time",
            "entry_time",
            "exit_time",
            "net_pnl",
            "gross_pnl",
            "pnl_pips",
        ]
        trades = pd.DataFrame(columns=columns)

    out = trades.copy()
    for column in ("signal_time", "entry_time", "exit_time"):
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], utc=True)
    if "symbol" not in out.columns:
        out["symbol"] = config.pair
    else:
        out["symbol"] = out["symbol"].fillna(config.pair).astype(str).str.upper()
    out["member_name"] = config.name
    out["strategy_name"] = config.strategy
    out["pair"] = config.pair.upper()
    out["timeframe"] = config.timeframe
    if "net_pnl" not in out.columns:
        out["net_pnl"] = 0.0
    out["net_pnl"] = out["net_pnl"].fillna(0.0).astype(float)
    if "exit_time" not in out.columns:
        raise ValueError(f"Trade artifact for {config.name} is missing required column 'exit_time'")
    out["trade_date"] = out["exit_time"].dt.normalize()
    return out.sort_values("exit_time").reset_index(drop=True)


def _build_daily_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float, name="net_pnl")
    series = trades.groupby("trade_date", sort=True)["net_pnl"].sum().astype(float)
    series.index = pd.to_datetime(series.index, utc=True)
    series.name = "net_pnl"
    return series


def _infer_usd_direction(pair: str, side: str) -> str | None:
    normalized_pair = str(pair or "").upper()
    normalized_side = str(side or "").lower()
    if len(normalized_pair) != 6 or normalized_side not in {"long", "short"}:
        return None
    base = normalized_pair[:3]
    quote = normalized_pair[3:]
    if base == "USD":
        return "usd_long" if normalized_side == "long" else "usd_short"
    if quote == "USD":
        return "usd_short" if normalized_side == "long" else "usd_long"
    return None


def _build_active_positions(trades: pd.DataFrame, config: PortfolioMemberConfig) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["date", "member_name", "strategy_name", "pair", "side", "usd_direction"])

    rows: list[dict[str, Any]] = []
    for trade in trades.itertuples(index=False):
        entry_time = getattr(trade, "entry_time", None)
        exit_time = getattr(trade, "exit_time", None)
        if pd.isna(entry_time) or pd.isna(exit_time):
            continue
        entry_day = pd.Timestamp(entry_time).normalize()
        exit_day = pd.Timestamp(exit_time).normalize()
        for day in pd.date_range(entry_day, exit_day, freq="D", tz="UTC"):
            rows.append(
                {
                    "date": day,
                    "member_name": config.name,
                    "strategy_name": config.strategy,
                    "pair": config.pair.upper(),
                    "side": getattr(trade, "side", None),
                    "usd_direction": _infer_usd_direction(config.pair, getattr(trade, "side", "")),
                }
            )

    active = pd.DataFrame(rows)
    if active.empty:
        return pd.DataFrame(columns=["date", "member_name", "strategy_name", "pair", "side", "usd_direction"])
    return active.drop_duplicates().sort_values(["date", "member_name"]).reset_index(drop=True)


def load_strategy_stream(config: PortfolioMemberConfig) -> StrategyStream:
    artifact_path = Path(config.artifact_path)
    trades = pd.read_parquet(artifact_path)
    normalized = _normalize_trades(trades, config)
    return StrategyStream(
        config=config,
        trades=normalized,
        daily_pnl=_build_daily_pnl(normalized),
        active_positions=_build_active_positions(normalized, config),
    )


def build_daily_pnl_matrix(streams: list[StrategyStream]) -> pd.DataFrame:
    if not streams:
        return pd.DataFrame()
    series = [stream.daily_pnl.rename(stream.name) for stream in streams]
    return pd.concat(series, axis=1).fillna(0.0).sort_index()


def build_active_positions_frame(streams: list[StrategyStream]) -> pd.DataFrame:
    frames = [stream.active_positions for stream in streams if not stream.active_positions.empty]
    if not frames:
        return pd.DataFrame(columns=["date", "member_name", "strategy_name", "pair", "side", "usd_direction"])
    return pd.concat(frames, ignore_index=True).sort_values(["date", "member_name"]).reset_index(drop=True)


def load_portfolio_candidates_config(path: str | Path) -> tuple[dict[str, PortfolioMemberConfig], list[PortfolioExperimentConfig]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    member_defs = raw.get("shared_members", {})
    if not isinstance(member_defs, dict) or not member_defs:
        raise ValueError("config/portfolio_candidates.yaml must define a non-empty 'shared_members' mapping")

    members: dict[str, PortfolioMemberConfig] = {}
    for name, payload in member_defs.items():
        payload = dict(payload or {})
        members[name] = PortfolioMemberConfig(
            name=name,
            strategy=payload["strategy"],
            pair=payload["pair"],
            timeframe=payload["timeframe"],
            artifact_path=payload["artifact_path"],
            archetype=payload.get("archetype"),
            metadata=dict(payload.get("metadata", {})),
        )

    experiments_raw = raw.get("experiments", [])
    if not isinstance(experiments_raw, list) or not experiments_raw:
        raise ValueError("config/portfolio_candidates.yaml must define a non-empty 'experiments' list")

    experiments: list[PortfolioExperimentConfig] = []
    for payload in experiments_raw:
        item = dict(payload or {})
        member_names = tuple(item["member_names"])
        experiments.append(
            PortfolioExperimentConfig(
                name=item["name"],
                member_names=member_names,
                weighting_method=item.get("weighting_method", "equal_weight"),
                max_weight_per_strategy=float(item.get("max_weight_per_strategy", 1.0)),
                rebalance_frequency=item.get("rebalance_frequency", "monthly"),
                lookback_days=int(item.get("lookback_days", 63)),
                max_weight_per_pair=item.get("max_weight_per_pair"),
                max_usd_direction_exposure=item.get("max_usd_direction_exposure"),
                max_active_strategies_per_pair=item.get("max_active_strategies_per_pair"),
                one_strategy_per_pair=bool(item.get("one_strategy_per_pair", False)),
                blocked_strategy_pairs=tuple(tuple(pair) for pair in item.get("blocked_strategy_pairs", [])),
                notes=item.get("notes"),
            )
        )
    return members, experiments
