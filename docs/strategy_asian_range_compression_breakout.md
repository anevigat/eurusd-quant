# Asian Range Compression Breakout Strategy Research Summary

## Strategy hypothesis
Original hypothesis:

- measure volatility compression during the Asian session
- define compression as Asian range relative to ATR
- trade breakout expansion during the London session when compression is detected

Motivation:

- previous strategy research showed time-of-day effects matter in EURUSD
- volatility regime might influence whether breakout behavior is tradable

## Implementation summary
Implemented MVP strategy:

- `strategy`: `asian_range_compression_breakout`
- Asian session: `00:00-06:00 UTC`
- breakout entry window: `07:00-10:00 UTC`
- breakout rules:
  - long: break above Asian high
  - short: break below Asian low
- compression condition:
  - `compression_ratio = asian_range / ATR`
- ATR period: `14`
- breakout buffer applied
- exits:
  - ATR-based stop
  - ATR-target take profit
  - max holding bars

## Dataset used

- EURUSD M15
- combined 2018-2024 dataset
- Dukascopy tick data converted into bid/ask-aware M15 bars

## Distribution analysis
Compression-ratio quantiles from historical analysis (`asian_range / ATR`):

- min: 2.40
- p5: 3.65
- p10: 4.02
- p20: 4.48
- p25: 4.69
- p50: 5.62
- p75: 6.83
- p90: 7.96
- p95: 8.88
- max: 16.10

Interpretation:

- typical Asian range is around 5-6x ATR in this dataset
- compression should therefore be defined with higher ratio thresholds than initially assumed

## Experiments performed
Compression regimes tested:

- `compression_ratio <= 4.0`
- `compression_ratio <= 4.5`
- `compression_ratio <= 4.7`

Dataset used for experiments:

- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`

## Results

| threshold | trades | win_rate | profit_factor | net_pnl |
|---|---:|---:|---:|---:|
| 4.0 | 1432 | 0.3582 | 0.8066 | -0.114859 |
| 4.5 | 1497 | 0.3641 | 0.8360 | -0.098478 |
| 4.7 | 1517 | 0.3685 | 0.8535 | -0.087986 |

## Interpretation

- the compression breakout hypothesis did not produce a profitable edge
- results remained negative even in the most permissive tested compression regime
- trade counts were large (~1500), which is sufficient for meaningful statistical evaluation
- lack of profitability is therefore unlikely to be a sample-size artifact

## Final conclusion
The Asian range compression breakout strategy was tested using empirically derived compression regimes on the 2018-2024 EURUSD dataset. The strategy did not demonstrate profitability under any tested regime.

Classification:

- researched but not promising

## Lessons learned

- volatility compression does not automatically imply breakout expansion in EURUSD
- empirical regime analysis is essential before defining compression thresholds
- large sample sizes help reject weak hypotheses quickly
- simple breakout logic is often insufficient even under favorable volatility regimes

## Future revisit options

- test on other FX pairs
- use different breakout confirmation logic
- combine compression with directional filters
- explore mean-reversion behavior after compression instead of breakout

## Related outputs

- `outputs/asian_range_compression_distribution/`
- `outputs/asian_compression_breakout_experiments/`
