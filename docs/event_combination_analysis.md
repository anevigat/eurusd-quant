# Event Combination Analysis

## Purpose

Single-event statistics can miss interactions between conditions. `scripts/analyze_event_combinations.py` measures forward returns after pairwise event combinations to discover richer edge structures.

This is a research/discovery tool only.

## Event combinations supported in v1

The analyzer evaluates these pairwise combinations:

1. `impulse + new_high/new_low`
2. `impulse + session_open`
3. `compression + session_open`
4. `compression + breakout(new_high/new_low)`

Event definitions are aligned with `scripts/analyze_event_returns.py`.

## Forward-return methodology

For each combination event:

- `return_1_bar`
- `return_4_bars`
- `return_8_bars`
- `adverse_move_4_bars`
- `adverse_move_8_bars`

Returns are ATR-normalized at event time.

## Directional normalization

Directional combinations (`up`/`down`) follow the same convention:

- positive return = continuation in event direction
- negative return = reversal against event direction

For `direction=none` combinations, returns are unaligned close-to-close effects.

## Edge scoring

Per combination bucket:

`edge_score = abs(median_return_4_bars) * log(sample_size)`

Top-edge view defaults to `sample_size >= 100`.

## Outputs

`outputs/event_combination_analysis/`

- `event_combinations.csv`
- `combination_bucket_summary.csv`
- `top_combination_edges.csv`
- `summary.json`

## Interpretation guidance

- prioritize combinations with robust sample size and favorable return/adverse profile
- treat low-sample combinations as exploratory
- validate top combinations in out-of-sample workflows before strategy implementation

## Limitations

- v1 supports only predefined pairwise combinations
- same-bar / ±1-bar alignment can still capture noisy co-occurrence
- in-sample ranking can surface false discoveries

## Converting combinations into strategy ideas

Practical path:

1. take top combination edges with strong sample support
2. convert combined condition into deterministic entry rule
3. choose exits from return/adverse distribution characteristics
4. run baseline + stress backtests before further refinement

## Example usage

```bash
python scripts/analyze_event_combinations.py \
  --bars data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/event_combination_analysis
```
