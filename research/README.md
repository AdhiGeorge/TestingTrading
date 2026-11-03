# XAUUSD Research Pipeline

Run from the repository root:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=research python3 research/data_loader.py .
PYTHONPATH=research python3 research/engine.py
PYTHONPATH=research python3 research/search.py
PYTHONPATH=research python3 research/reporting.py
```

The loader recursively reads the immutable source CSVs, converts millisecond Unix timestamps to UTC, derives New York and IST timestamps, validates OHLC/gaps/duplicates, and writes a cache when Parquet support is installed. The engine resamples from the 17:00 New York daily open and runs the conservative baseline. The search runs the staged ablation, greedy, capped interaction, stress, gate, and walk-forward tables. Reporting creates directional timing tables, equity/drawdown charts, monthly heatmaps, and 30 sample trade charts.

## Current state

- Primary scaling: spread `0.0075% × price`; stop buffer `0.15 × H1 ATR(14)`; minimum stop `0.50 × H1 ATR(14)`; cap `5 × H1 ATR(14)`; gap filter `1 × M5 ATR(14)`.
- Baseline result: 126 trades after single-order overlap enforcement; 61 buys and 65 sells.
- Staged search: 49 trials logged.
- Final gated candidates: 0.
- Lock-out set: not touched because no candidate passed the required screens.

SMT and news-calendar modules are skipped because no XAGUSD/DXY/EURUSD or economic-calendar files were supplied.
