# Event Combination Analysis v2 (Cross Pair)

## Purpose

Event Combination Analysis v2 extends the original event-combination workflow to:

- run automatically across multiple pair/range datasets
- test richer event families and pairwise event interactions
- rank candidate edges per dataset
- compare top edges across pairs and ranges

This is a research discovery tool, not a tradable strategy implementation.

## Datasets

The v2 runner auto-detects these datasets and skips missing ones:

- `EURUSD_historical` -> `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- `GBPUSD_historical` -> `data/bars/15m/gbpusd_bars_15m_2018_2024.parquet`
- `EURUSD_forward` -> `data/bars/15m/eurusd_bars_15m_2025_now.parquet`
- `GBPUSD_forward` -> `data/bars/15m/gbpusd_bars_15m_2025_now.parquet`

## Event Families in v2

1. `impulse` (ATR-normalized)
   - buckets: `1.0-1.5 ATR`, `1.5-2.0 ATR`, `>2.0 ATR`
   - directions: `up`, `down`
2. `compression` (ATR / rolling median ATR)
   - buckets: `<=p10`, `p10-p25`, `p25-p50`
3. `new_high_low`
   - `new_high_20`, `new_low_20`
4. `session_open`
   - `london_open`, `new_york_open`
5. `atr_spike`
   - buckets: `>1.5`, `>2.0`
6. `vwap_deviation_session` (VWAP proxy via cumulative typical-price mean)
   - buckets: `2.0-3.0 ATR`, `>3.0 ATR`
   - directions: `positive`, `negative`
7. `prior_day_break`
   - `break_above_prior_day_high`, `break_below_prior_day_low`

## Combination Groups

The runner evaluates at least:

- `impulse × session_open`
- `impulse × new_high_low`
- `compression × session_open`
- `compression × new_high_low`
- `compression × prior_day_break`
- `atr_spike × new_high_low`
- `vwap_deviation × session_open`
- `impulse × vwap_deviation`

Alignment rule:

- same bar or within a configurable `N`-bar window (`--alignment-window-bars`, default `1`)

## Forward-Return Method

Per detected combination event:

- `return_1_bar`, `return_4_bars`, `return_8_bars`, `return_16_bars`
- `adverse_move_4_bars`, `adverse_move_8_bars`, `adverse_move_16_bars`

All returns are ATR-normalized.

Directional normalization:

- directional combinations use normalized sign so positive values indicate continuation in event direction
- non-directional combinations (`direction=none`) use unaligned ATR-normalized close-to-close returns

## Ranking and Quality

Combination summary includes:

- `edge_score = abs(median_return_4_bars) * log(sample_size)`
- `quality_score = abs(median_return_4_bars) / median_adverse_move_4_bars`

Top-edge filtering:

- requires `sample_size >= 200` by default

## Conditional Enrichment

After ranking top combinations, v2 computes conditional edge slices with one added factor:

- session regime (`london_session`, `new_york_session`)
- ATR regime (`high_atr`, `normal_atr`)
- impulse size regime (`large_impulse`, `medium_impulse`)

This produces `top_conditional_edges_v2.csv`.

## Cross-Pair Comparison

`analyze_cross_pair_event_edges.py` loads per-dataset top-edge outputs and generates:

- `cross_pair_top_edges.csv`
- `cross_pair_edge_matrix.csv` (combination rows x dataset columns, values = `median_return_4_bars`)
- `cross_pair_summary.json`

It highlights:

- edges shared across EURUSD and GBPUSD
- edges that appear in both historical and forward ranges

## Interpretation Guidance

- Stronger candidates generally combine meaningful `edge_score`, good `quality_score`, and broad pair/range presence.
- Forward datasets are shorter; treat forward-only winners as provisional.
- Combination mining involves multiple testing; treat outputs as hypothesis generation, not confirmation.

## Example Strategy Ideas

- London/NY transition impulse fades only when combined with extreme VWAP deviation.
- Compression breakouts conditioned on prior-day breaks and high ATR regime.
- Breakout-failure variants from `atr_spike × new_high_low` edges.
