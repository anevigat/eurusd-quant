# eurusd_quant

Minimal MVP for backtesting a EURUSD M15 Session Range Breakout strategy with a realistic bar-based execution simulator.

## Requirements

- Python 3.11+
- `pandas`, `numpy`, `pyarrow`, `pyyaml`, `pytest`

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Run tests:

```bash
pytest
```

Run backtest:

```bash
python scripts/run_backtest.py \
  --input tests/fixtures/sample_bars_15m.parquet \
  --strategy session_breakout \
  --output-dir outputs
```

Outputs:

- `outputs/trades.parquet`
- `outputs/metrics.json`

