from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FORWARD_HORIZONS = (1, 2, 4, 8)
PRIMARY_CONTEXTS = ("London", "early New York", "London -> New York boundary")
POOLED_MIN_CANDIDATE_SAMPLE = 400
PAIR_MIN_CANDIDATE_SAMPLE = 200


@dataclass(frozen=True)
class RegionSpec:
    region_id: str
    candidate_description: str
    pair_scope: str
    session_context: str
    range_regime: str
    volatility_regime: str
    breach_type: str
    magnitude_bucket: str
    evaluation_horizon: str


def _pip_multiplier(pair: str) -> float:
    return 100.0 if pair.endswith("JPY") else 10000.0


def assign_time_context(frame: pd.DataFrame) -> pd.Series:
    time_context = frame["session"].map({"asia": "Asia", "london": "London", "new_york": "New York"})
    time_context = time_context.fillna("Unknown")
    boundary_mask = frame["transition_context"] == "london_to_new_york_boundary"
    early_new_york_mask = (frame["session"] == "new_york") & (frame["session_subcontext"] == "early_session")
    time_context.loc[boundary_mask] = "London -> New York boundary"
    time_context.loc[early_new_york_mask] = "early New York"
    return time_context


def assign_expanded_intensity(frame: pd.DataFrame) -> pd.Series:
    session_range = frame["session_range"].astype(float)
    ranks = frame.groupby("pair")["session_range"].rank(method="average", pct=True)
    intensity = pd.Series(
        np.where(ranks >= 2 / 3, "strongly_expanded", "moderately_expanded"),
        index=frame.index,
        dtype="object",
    )
    intensity[session_range.isna()] = "unknown"
    return intensity


def load_base_candidate_region(diagnostics_root: Path) -> pd.DataFrame:
    inventory = pd.read_csv(
        diagnostics_root / "contextual_breaches" / "contextual_breach_inventory.csv",
        parse_dates=["timestamp", "fx_session_date"],
    )
    outcomes = pd.read_csv(diagnostics_root / "contextual_breaches" / "contextual_breach_outcomes.csv")
    session_states = pd.read_csv(
        diagnostics_root / "session_state_transitions" / "session_state_inventory.csv",
        parse_dates=["fx_session_date"],
    )

    region = inventory.merge(outcomes, on="event_id", how="inner")
    region = region[region["range_regime"] == "expanded"].copy()
    session_lookup = session_states[["pair", "fx_session_date", "session", "session_range"]].drop_duplicates()
    region = region.merge(session_lookup, on=["pair", "fx_session_date", "session"], how="left")
    region["time_context"] = assign_time_context(region)
    region["expanded_intensity"] = assign_expanded_intensity(region)
    region["pip_multiplier"] = region["pair"].map(_pip_multiplier)
    region["year"] = region["timestamp"].dt.year.astype(int)
    region["pair_scope"] = region["pair"]
    return region


def select_inventory_columns(region: pd.DataFrame) -> pd.DataFrame:
    renamed = region.rename(
        columns={
            "event_type": "breach_type",
            "direction": "breach_direction",
            "breach_magnitude_atr": "breach_magnitude_atr",
            "forward_return_1": "forward_return_h1",
            "forward_return_2": "forward_return_h2",
            "forward_return_4": "forward_return_h4",
            "forward_return_8": "forward_return_h8",
        }
    )
    return renamed[
        [
            "event_id",
            "pair",
            "timestamp",
            "session",
            "time_context",
            "session_subcontext",
            "transition_context",
            "volatility_regime",
            "range_regime",
            "expanded_intensity",
            "breach_type",
            "event_class",
            "breach_direction",
            "magnitude_bucket",
            "breach_magnitude_pips",
            "breach_magnitude_atr",
            "lookback_window",
            "forward_return_h1",
            "forward_return_h2",
            "forward_return_h4",
            "forward_return_h8",
            "aligned_forward_return_1",
            "aligned_forward_return_2",
            "aligned_forward_return_4",
            "aligned_forward_return_8",
            "continuation_flag_1",
            "continuation_flag_2",
            "continuation_flag_4",
            "continuation_flag_8",
            "reversal_flag_1",
            "reversal_flag_2",
            "reversal_flag_4",
            "reversal_flag_8",
            "mfe_1",
            "mfe_2",
            "mfe_4",
            "mfe_8",
            "mae_1",
            "mae_2",
            "mae_4",
            "mae_8",
        ]
    ].sort_values(["pair", "timestamp", "event_id"]).reset_index(drop=True)


def _outcome_col(horizon: int) -> str:
    return f"aligned_forward_return_{horizon}"


def _raw_return_col(horizon: int) -> str:
    return f"forward_return_{horizon}"


def _continuation_col(horizon: int) -> str:
    return f"continuation_flag_{horizon}"


def _reversal_col(horizon: int) -> str:
    return f"reversal_flag_{horizon}"


def _mfe_col(horizon: int) -> str:
    return f"mfe_{horizon}"


def _mae_col(horizon: int) -> str:
    return f"mae_{horizon}"


def summarize_candidate_region(frame: pd.DataFrame, *, horizon: int) -> dict[str, Any]:
    outcome_col = _outcome_col(horizon)
    raw_return_col = _raw_return_col(horizon)
    continuation_col = _continuation_col(horizon)
    reversal_col = _reversal_col(horizon)
    mfe_col = _mfe_col(horizon)
    mae_col = _mae_col(horizon)

    usable = frame.dropna(subset=[outcome_col]).copy()
    sample_count = int(len(usable))
    if sample_count == 0:
        return {
            "sample_count": 0,
            "mean_return": np.nan,
            "median_return": np.nan,
            "positive_fraction": np.nan,
            "continuation_fraction": np.nan,
            "reversal_fraction": np.nan,
            "mean_absolute_move": np.nan,
            "mean_favorable_excursion": np.nan,
            "mean_adverse_excursion": np.nan,
            "std_return": np.nan,
            "se_return": np.nan,
            "p10_return": np.nan,
            "p25_return": np.nan,
            "p75_return": np.nan,
            "p90_return": np.nan,
            "mean_return_pips": np.nan,
        }

    aligned = usable[outcome_col].astype(float)
    raw = usable[raw_return_col].astype(float)
    std_return = float(aligned.std(ddof=1)) if sample_count > 1 else np.nan
    se_return = float(std_return / np.sqrt(sample_count)) if sample_count > 1 else np.nan
    return {
        "sample_count": sample_count,
        "low_sample": sample_count < 30,
        "mean_return": float(aligned.mean()),
        "median_return": float(aligned.median()),
        "positive_fraction": float((raw > 0).mean()),
        "continuation_fraction": float(usable[continuation_col].mean()),
        "reversal_fraction": float(usable[reversal_col].mean()),
        "mean_absolute_move": float(aligned.abs().mean()),
        "mean_favorable_excursion": float(usable[mfe_col].mean()),
        "mean_adverse_excursion": float(usable[mae_col].mean()),
        "std_return": std_return,
        "se_return": se_return,
        "p10_return": float(aligned.quantile(0.10)),
        "p25_return": float(aligned.quantile(0.25)),
        "p75_return": float(aligned.quantile(0.75)),
        "p90_return": float(aligned.quantile(0.90)),
        "mean_return_pips": float((aligned * usable["pip_multiplier"]).mean()),
    }


def summarize_grouped_regions(
    frame: pd.DataFrame,
    *,
    group_cols: list[str],
    breakdown_family: str,
    horizon: int = 4,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, subset in frame.groupby(group_cols, dropna=False):
        values = key if isinstance(key, tuple) else (key,)
        row = {
            "breakdown_family": breakdown_family,
            "pair": "ALL",
            "time_context": "all",
            "event_type": "all",
            "breach_direction": "all",
            "magnitude_bucket": "all",
            "volatility_regime": "all",
            "range_regime": "expanded",
            "expanded_intensity": "all",
            "lookback_window": "all",
            "evaluation_horizon": f"h{horizon}",
        }
        for col, value in zip(group_cols, values, strict=False):
            row[col] = value
        row.update(summarize_candidate_region(subset, horizon=horizon))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["mean_return", "sample_count"], ascending=[False, False]).reset_index(
        drop=True
    )


def build_candidate_region_subregions(region: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("pair", ["pair"]),
        ("time_context", ["time_context"]),
        ("event_type", ["event_type"]),
        ("breach_direction", ["direction"]),
        ("magnitude_bucket", ["magnitude_bucket"]),
        ("volatility_regime", ["volatility_regime"]),
        ("lookback_window", ["lookback_window"]),
        ("expanded_intensity", ["expanded_intensity"]),
        ("pair__time_context", ["pair", "time_context"]),
        ("pair__event_type", ["pair", "event_type"]),
        ("time_context__event_type", ["time_context", "event_type"]),
        ("time_context__expanded_intensity__event_type", ["time_context", "expanded_intensity", "event_type"]),
        (
            "pair__time_context__expanded_intensity__event_type",
            ["pair", "time_context", "expanded_intensity", "event_type"],
        ),
        (
            "pair__time_context__expanded_intensity__direction",
            ["pair", "time_context", "expanded_intensity", "direction"],
        ),
        (
            "time_context__expanded_intensity__magnitude_bucket",
            ["time_context", "expanded_intensity", "magnitude_bucket"],
        ),
        (
            "pair__time_context__expanded_intensity__magnitude_bucket",
            ["pair", "time_context", "expanded_intensity", "magnitude_bucket"],
        ),
    ]
    tables = [summarize_grouped_regions(region, group_cols=cols, breakdown_family=family) for family, cols in specs]
    subregions = pd.concat(tables, ignore_index=True)
    return subregions.rename(columns={"direction": "breach_direction"}).sort_values(
        ["breakdown_family", "sample_count", "mean_return"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def build_pair_breakdown(region: pd.DataFrame) -> pd.DataFrame:
    return summarize_grouped_regions(region, group_cols=["pair"], breakdown_family="pair_breakdown", horizon=4)


def build_time_of_day_breakdown(region: pd.DataFrame) -> pd.DataFrame:
    time_df = summarize_grouped_regions(region, group_cols=["time_context"], breakdown_family="time_context", horizon=4)
    return time_df[time_df["time_context"].isin(["Asia", "London", "New York", "early New York", "London -> New York boundary"])]


def build_regime_breakdown(region: pd.DataFrame) -> pd.DataFrame:
    tables = [
        summarize_grouped_regions(region, group_cols=["volatility_regime"], breakdown_family="volatility_regime", horizon=4),
        summarize_grouped_regions(region, group_cols=["expanded_intensity"], breakdown_family="expanded_intensity", horizon=4),
        summarize_grouped_regions(
            region,
            group_cols=["volatility_regime", "expanded_intensity"],
            breakdown_family="volatility__expanded_intensity",
            horizon=4,
        ),
    ]
    return pd.concat(tables, ignore_index=True).sort_values(
        ["breakdown_family", "mean_return", "sample_count"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def _candidate_profile_row(region_id: str, description: str, frame: pd.DataFrame, horizon: int) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "region_description": description,
        "evaluation_horizon": f"h{horizon}",
        **summarize_candidate_region(frame, horizon=horizon),
    }


def build_candidate_outcome_profiles(region: pd.DataFrame, definitions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in FORWARD_HORIZONS:
        rows.append(_candidate_profile_row("base_region", "Expanded contextual breaches base region", region, horizon))

    for definition in definitions.to_dict(orient="records"):
        subset = filter_region(
            region,
            pair_scope=definition["pair_scope"],
            session_context=definition["session_context"],
            expanded_intensity=definition["range_regime"],
            breach_type=definition["breach_type"],
            magnitude_bucket=definition["magnitude_bucket"],
            volatility_regime=definition["volatility_regime"],
        )
        for horizon in FORWARD_HORIZONS:
            rows.append(
                _candidate_profile_row(
                    definition["candidate_id"],
                    definition["candidate_description"],
                    subset,
                    horizon,
                )
            )
    return pd.DataFrame(rows).sort_values(["region_id", "evaluation_horizon"]).reset_index(drop=True)


def filter_region(
    region: pd.DataFrame,
    *,
    pair_scope: str = "ALL",
    session_context: str = "all",
    expanded_intensity: str = "expanded",
    breach_type: str = "all",
    magnitude_bucket: str = "all",
    volatility_regime: str = "all",
) -> pd.DataFrame:
    mask = pd.Series(True, index=region.index)
    if pair_scope != "ALL":
        mask &= region["pair"] == pair_scope
    if session_context != "all":
        mask &= region["time_context"] == session_context
    if expanded_intensity in {"moderately_expanded", "strongly_expanded"}:
        mask &= region["expanded_intensity"] == expanded_intensity
    if breach_type != "all":
        mask &= region["event_type"] == breach_type
    if magnitude_bucket != "all":
        mask &= region["magnitude_bucket"] == magnitude_bucket
    if volatility_regime != "all":
        mask &= region["volatility_regime"] == volatility_regime
    return region[mask].copy()


def generate_edge_candidate_definitions(region: pd.DataFrame) -> pd.DataFrame:
    base_metrics = summarize_candidate_region(region, horizon=4)
    search_rows: list[dict[str, Any]] = []

    for pair_scope, subset, min_sample in (
        ("ALL", region, POOLED_MIN_CANDIDATE_SAMPLE),
        ("USDJPY", region[region["pair"] == "USDJPY"].copy(), PAIR_MIN_CANDIDATE_SAMPLE),
    ):
        grouped = subset.groupby(
            ["time_context", "expanded_intensity", "event_type", "magnitude_bucket"],
            dropna=False,
        )
        for key, group in grouped:
            time_context, expanded_intensity, event_type, magnitude_bucket = key
            if pair_scope == "ALL" and time_context not in PRIMARY_CONTEXTS:
                continue
            if expanded_intensity != "strongly_expanded":
                continue
            h1 = summarize_candidate_region(group, horizon=1)
            h2 = summarize_candidate_region(group, horizon=2)
            h4 = summarize_candidate_region(group, horizon=4)
            h8 = summarize_candidate_region(group, horizon=8)
            if h4["sample_count"] < min_sample:
                continue
            if h4["mean_return"] <= base_metrics["mean_return"]:
                continue
            if h4["continuation_fraction"] <= base_metrics["continuation_fraction"]:
                continue
            if min(h1["mean_return"], h2["mean_return"], h4["mean_return"], h8["mean_return"]) <= 0:
                continue

            score = h4["mean_return"] / h4["se_return"] if pd.notna(h4["se_return"]) and h4["se_return"] > 0 else np.nan
            search_rows.append(
                {
                    "pair_scope": pair_scope,
                    "session_context": time_context,
                    "range_regime": expanded_intensity,
                    "volatility_regime": "all",
                    "breach_type": event_type,
                    "magnitude_bucket": magnitude_bucket,
                    "evaluation_horizon": "h4",
                    "sample_count": h4["sample_count"],
                    "mean_outcome": h4["mean_return"],
                    "positive_fraction": h4["positive_fraction"],
                    "continuation_fraction": h4["continuation_fraction"],
                    "h1_mean_outcome": h1["mean_return"],
                    "h2_mean_outcome": h2["mean_return"],
                    "h8_mean_outcome": h8["mean_return"],
                    "signal_score": score,
                }
            )

    summary = pd.DataFrame(search_rows)
    if summary.empty:
        return summary

    summary = summary.sort_values(["signal_score", "mean_outcome", "sample_count"], ascending=[False, False, False])
    pooled = summary[summary["pair_scope"] == "ALL"].drop_duplicates(
        subset=["pair_scope", "session_context", "breach_type"]
    ).head(4)
    usdjpy = summary[summary["pair_scope"] == "USDJPY"].drop_duplicates(
        subset=["pair_scope", "session_context", "breach_type"]
    ).head(1)
    definitions = pd.concat([pooled, usdjpy], ignore_index=True)
    definitions = definitions.drop_duplicates(
        subset=["pair_scope", "session_context", "range_regime", "breach_type", "magnitude_bucket"]
    ).reset_index(drop=True)
    definitions["candidate_id"] = [f"ecb_{index + 1:02d}" for index in range(len(definitions))]
    definitions["candidate_description"] = definitions.apply(
        lambda row: (
            f"{row['pair_scope']} {row['session_context']} {row['range_regime']} "
            f"{row['breach_type']} {row['magnitude_bucket']} candidate"
        ),
        axis=1,
    )
    keep_cols = [
        "candidate_id",
        "candidate_description",
        "pair_scope",
        "session_context",
        "range_regime",
        "volatility_regime",
        "breach_type",
        "magnitude_bucket",
        "evaluation_horizon",
        "sample_count",
        "mean_outcome",
        "positive_fraction",
        "continuation_fraction",
        "h1_mean_outcome",
        "h2_mean_outcome",
        "h8_mean_outcome",
        "signal_score",
    ]
    return definitions[keep_cols]
