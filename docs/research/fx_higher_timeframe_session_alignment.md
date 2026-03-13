# FX Higher-Timeframe Session Alignment

## Problem

The initial higher-timeframe aggregation for trend research used plain UTC resampling for `1d` and `4h` bars. That is convenient, but it is not a great default for FX because the market week and the de facto trading day do not roll at midnight UTC.

## Confirmed Repo Convention

This repo's 15m bars use:

- UTC timestamps
- bar-open timestamps
- an existing FX market-week boundary at `22:00 UTC`

That convention is already visible upstream:

- `scripts/build_bars.py` floors tick timestamps to the 15m bar open in UTC
- the historical EURUSD 15m dataset starts at `2018-01-01 22:00:00+00:00`
- the downloader/docs already treat `Sunday < 22:00 UTC` and `Friday > 22:00 UTC` as closed-market hours

## Convention Chosen In This Patch

Higher-timeframe aggregation now uses a fixed `22:00 UTC` session rollover anchor.

- daily bars open at `22:00 UTC`
- 4h bars align to the same boundary, so bucket starts are `22:00`, `02:00`, `06:00`, `10:00`, `14:00`, and `18:00 UTC`

This patch intentionally keeps the rule fixed in UTC. It does not attempt full DST-aware New York-close handling. If later research needs exact New York-close alignment through DST transitions, that should be a separate, explicit enhancement.

## Why It Matters

For FX trend and momentum research, higher-timeframe bucket boundaries affect:

- daily close placement
- Donchian breakout levels
- moving-average inputs
- trailing return windows
- comparability with standard FX session conventions

Using a fixed session rollover is a correctness improvement over naive midnight-UTC grouping, even before any deeper trend-family refinement.

## Scope

This is a data-integrity patch only.

- no strategy logic changes
- no promotion threshold changes
- no re-optimization
- no claim that existing Phase 2 results changed promotion status

## Operational Note

`scripts/prepare_higher_timeframe_bars.py` now writes a sidecar metadata file next to each generated parquet file so the aggregation convention is recoverable later.

Small validation artifacts for this patch were generated under:

- `outputs/data_validation/session_aligned_htf/`
- `outputs/diagnostics/session_aligned_htf_smoke/`
