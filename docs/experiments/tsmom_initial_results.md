# Initial FX Trend / Momentum Results

## Commands Run

### Build daily bars

```bash
.venv/bin/python scripts/prepare_higher_timeframe_bars.py \
  --input-file data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-file data/bars/1d/eurusd_bars_1d_2018_2024.parquet \
  --timeframe 1d
```

```bash
.venv/bin/python scripts/prepare_higher_timeframe_bars.py \
  --input-file data/bars/15m/gbpusd_bars_15m_2018_2024.parquet \
  --output-file data/bars/1d/gbpusd_bars_1d_2018_2024.parquet \
  --timeframe 1d
```

### Smoke backtests

```bash
.venv/bin/python scripts/run_backtest.py --input data/bars/1d/eurusd_bars_1d_2018_2024.parquet --strategy tsmom_ma_cross --output-dir outputs/trend_backtests/tsmom_ma_cross
.venv/bin/python scripts/run_backtest.py --input data/bars/1d/eurusd_bars_1d_2018_2024.parquet --strategy tsmom_donchian --output-dir outputs/trend_backtests/tsmom_donchian
.venv/bin/python scripts/run_backtest.py --input data/bars/1d/eurusd_bars_1d_2018_2024.parquet --strategy tsmom_return_sign --output-dir outputs/trend_backtests/tsmom_return_sign
```

### Sweeps

```bash
.venv/bin/python scripts/run_trend_strategy_sweep.py --strategy tsmom_ma_cross --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --output-dir outputs/trend_sweeps/tsmom_ma_cross
.venv/bin/python scripts/run_trend_strategy_sweep.py --strategy tsmom_donchian --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --output-dir outputs/trend_sweeps/tsmom_donchian
.venv/bin/python scripts/run_trend_strategy_sweep.py --strategy tsmom_return_sign --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --output-dir outputs/trend_sweeps/tsmom_return_sign
```

### Walk-forward validation

```bash
.venv/bin/python scripts/run_walk_forward_validation.py --strategy tsmom_ma_cross --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --input-configs outputs/trend_sweeps/tsmom_ma_cross/top_configs.csv --top-n 1 --train-years 3 --test-months 6 --output-dir outputs/trend_walk_forward/tsmom_ma_cross
.venv/bin/python scripts/run_walk_forward_validation.py --strategy tsmom_donchian --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --input-configs outputs/trend_sweeps/tsmom_donchian/top_configs.csv --top-n 1 --train-years 3 --test-months 6 --output-dir outputs/trend_walk_forward/tsmom_donchian
.venv/bin/python scripts/run_walk_forward_validation.py --strategy tsmom_return_sign --bars data/bars/1d/eurusd_bars_1d_2018_2024.parquet --input-configs outputs/trend_sweeps/tsmom_return_sign/top_configs.csv --top-n 1 --train-years 3 --test-months 6 --output-dir outputs/trend_walk_forward/tsmom_return_sign
```

### Cross-pair spot checks

```bash
.venv/bin/python scripts/run_walk_forward_validation.py --strategy tsmom_ma_cross --bars data/bars/1d/gbpusd_bars_1d_2018_2024.parquet --input-configs outputs/trend_sweeps/tsmom_ma_cross/top_configs.csv --top-n 1 --train-years 3 --test-months 6 --output-dir outputs/trend_cross_pair/tsmom_ma_cross_gbpusd
.venv/bin/python scripts/run_walk_forward_validation.py --strategy tsmom_return_sign --bars data/bars/1d/gbpusd_bars_1d_2018_2024.parquet --input-configs outputs/trend_sweeps/tsmom_return_sign/top_configs.csv --top-n 1 --train-years 3 --test-months 6 --output-dir outputs/trend_cross_pair/tsmom_return_sign_gbpusd
```

## Datasets Used

- EURUSD daily bars: `data/bars/1d/eurusd_bars_1d_2018_2024.parquet`
- GBPUSD daily bars: `data/bars/1d/gbpusd_bars_1d_2018_2024.parquet`

USDJPY and AUDUSD were targeted for later spot checks, but ready local higher-timeframe bars were not available in this branch. The cross-pair check in this PR is therefore limited to GBPUSD.

## Sweep Summary

### `tsmom_ma_cross`

- best config: `fast=20`, `slow=50`, `atr_stop_multiple=1.5`, `trailing_stop=true`
- in-sample summary: trades=`396`, PF=`1.1432`, net_pnl=`0.183034`, max_dd=`0.115710`
- interpretation: moderate daily trend-following behavior exists, but drawdown is still material

### `tsmom_donchian`

- best config: `breakout_window=55`, `atr_stop_multiple=1.5`, `trailing_stop=false`
- in-sample summary: trades=`34`, PF=`1.3313`, net_pnl=`0.085747`, max_dd=`0.154894`
- interpretation: strongest raw PF, but the sample is thin and fragile

### `tsmom_return_sign`

- best config: `lookback_window=20`, `return_threshold=0.0`, `atr_stop_multiple=1.5`, `trailing_stop=true`
- in-sample summary: trades=`508`, PF=`1.0594`, net_pnl=`0.082512`, max_dd=`0.181043`
- interpretation: broad persistence signal exists, but edge size is modest

## Walk-Forward Summary

### `tsmom_ma_cross`

- config hash: `c4583145efba`
- OOS trades=`141`
- OOS PF=`1.3655`
- OOS net_pnl=`0.152996`
- OOS expectancy=`0.001085`
- OOS max_dd=`0.053578`
- promotion result: `rejected`
- failure reason: insufficient OOS trade count by current gate, insufficient trades per year, drawdown above threshold, and year concentration issues

### `tsmom_donchian`

- config hash: `4e8c96c6bfdc`
- OOS trades=`16`
- OOS PF=`0.7004`
- OOS net_pnl=`-0.032471`
- OOS expectancy=`-0.002029`
- OOS max_dd=`0.046981`
- promotion result: `rejected`
- failure reason: too few trades and weak OOS performance

### `tsmom_return_sign`

- config hash: `4708f4ad8c09`
- OOS trades=`208`
- OOS PF=`1.2440`
- OOS net_pnl=`0.132989`
- OOS expectancy=`0.000639`
- OOS max_dd=`0.086719`
- promotion result: `rejected`
- failure reason: trades were adequate, but drawdown and year concentration still failed the current gates

## Cross-Pair Spot Check Summary

### `tsmom_ma_cross` on GBPUSD

- same EURUSD-selected config
- OOS trades=`149`
- OOS PF=`1.2235`
- OOS net_pnl=`0.147321`
- OOS max_dd=`0.092066`
- result: still rejected under current gates, but the direction of performance was not purely EURUSD-specific

### `tsmom_return_sign` on GBPUSD

- same EURUSD-selected config
- OOS trades=`204`
- OOS PF=`1.1416`
- OOS net_pnl=`0.118391`
- OOS max_dd=`0.085765`
- result: also rejected under current gates, but GBPUSD did show a similar moderate trend-following profile

## What Passed / What Failed

Passed:

- all three variants were implemented and integrated into the shared backtest + Phase 1 validation pipeline
- each variant received at least one EURUSD walk-forward run
- the strongest two variants retained PF above 1 in EURUSD and GBPUSD walk-forward checks

Failed:

- none of the three variants passed the current promotion framework
- Donchian is too sparse in current form
- MA crossover and return-sign still exceed the current drawdown and concentration gates

## Current Assessment

- `tsmom_ma_cross`: continue testing / refine
- `tsmom_donchian`: reject in current form
- `tsmom_return_sign`: continue testing / refine

## Conclusion

This phase did add something useful: a daily trend family that behaves differently from the repo's intraday reversal tree. The family is not promotable yet, but MA crossover and return-sign both merit continued research because they showed positive OOS behavior on EURUSD and a non-trivial GBPUSD echo. Donchian breakout did not survive the sample-size and OOS quality bar.
