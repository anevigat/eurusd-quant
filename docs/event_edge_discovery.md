# Event Edge Discovery

## Concept

`scripts/discover_event_edges.py` turns event-bucket summary statistics into ranked edge candidates.

It consumes `event_bucket_summary.csv` from the Event Return Analyzer and highlights the most statistically interesting continuation and reversal buckets.

This is a research/discovery layer, not a tradable strategy.

## Scoring formula

For each event bucket:

`edge_score = abs(median_return_4_bars) * log(sample_size)`

Rationale:

- `abs(median_return_4_bars)` measures effect magnitude
- `log(sample_size)` rewards reliability while avoiding linear overweighting of very large samples

The script filters to `sample_size >= 200` by default before ranking.

## Continuation vs reversal interpretation

- continuation bucket: `median_return_4_bars > 0`
- reversal bucket: `median_return_4_bars < 0`

Directional interpretation comes from the analyzer normalization:

- for directional events (`up`/`down`), positive return means continuation in event direction
- negative return means reversal against event direction

## Outputs

`outputs/event_edge_discovery/`

- `top_continuation_edges.csv`
- `top_reversal_edges.csv`
- `edge_candidates.json`

`edge_candidates.json` includes top candidate edges with:

- edge type (`continuation` or `reversal`)
- strength and sample context
- suggested strategy family labels (`impulse_fade`, `volatility_breakout`, `breakout_failure`, `experimental`)

## Limitations

- multiple bucket scans can produce false positives
- rankings are in-sample and exploratory
- strong scores still require out-of-sample validation and robust implementation constraints

## Converting edges into strategies

Practical flow:

1. pick high-score buckets with sufficient sample size
2. translate event definition into deterministic entry rule
3. define exit assumptions from return/adverse profiles
4. run baseline backtest and stress tests
5. reject quickly if edge decays under realistic execution assumptions

## Example usage

```bash
python scripts/discover_event_edges.py \
  --input outputs/event_return_analyzer/event_bucket_summary.csv \
  --output-dir outputs/event_edge_discovery
```
