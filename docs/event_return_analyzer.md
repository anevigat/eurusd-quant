# Event Return Analyzer

## Purpose

`scripts/analyze_event_returns.py` is a reusable research/discovery tool that measures forward return distributions after specific event types on EURUSD M15 data.

It is not a strategy implementation. The goal is to surface statistical asymmetries that may justify later strategy prototypes.

## Event families supported in v1

1. Impulse events
- rolling move over the last 4 bars
- event strength in ATR units:
  - `abs(close_now - close_4_bars_ago) / ATR(14)`
- buckets:
  - `1.0-1.5_atr`
  - `1.5-2.0_atr`
  - `>2.0_atr`
- directions:
  - `up`
  - `down`

2. Range compression events
- compression ratio:
  - `ATR(14) / rolling_median_ATR(40)`
- buckets:
  - `<=p10`
  - `p10-p25`
  - `p25-p50`
- direction:
  - `none`

3. New high / new low events
- lookback: 20 bars
- events:
  - `new_high_20` when current high exceeds previous 20-bar high
  - `new_low_20` when current low breaches previous 20-bar low
- directions:
  - `up`
  - `down`

4. Session open events
- first 15m bar of:
  - London open (`07:00 UTC`)
  - New York open (`13:00 UTC`)
- direction:
  - `none`

## Forward-return methodology

For each event occurrence:

- `return_1_bar`
- `return_4_bars`
- `return_8_bars`
- `adverse_move_4_bars`
- `adverse_move_8_bars`

Returns and adverse moves are expressed in ATR units using ATR at event time.

## Directional normalization

For directional events (`up`/`down`):

- positive return = continuation in event direction
- negative return = reversal against event direction

For non-directional events (`direction=none`), returns are unaligned close-to-close moves in ATR units.

## Output artifacts

Saved under `outputs/event_return_analyzer/`:

- `event_returns.csv` (one row per event occurrence)
- `event_bucket_summary.csv` (grouped distribution summary)
- `summary.json` (high-level totals and strongest buckets)

## Interpreting results

- positive `median_return_4_bars` in directional buckets implies continuation tendency
- negative `median_return_4_bars` in directional buckets implies reversal tendency
- buckets with small sample counts should be treated as exploratory only
- use sample-size thresholds before drawing conclusions

## Notes on false discoveries

This tool scans multiple event families and buckets, so some strong-looking buckets can occur by chance.

Practical guardrails:

- prioritize buckets with robust sample size
- validate effects out-of-sample
- avoid immediate strategy implementation without additional confirmation

## Example usage

```bash
python scripts/analyze_event_returns.py \
  --bars data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/event_return_analyzer
```
