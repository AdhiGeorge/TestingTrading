# XAUUSD M5 Bid Data-Quality Report

**Inspection date:** 2026-11-02 19:58 IST  
**Source:** repository CSV files, read-only; raw files were not modified.

## Summary

The dataset is readable and covers 2015-01-01 through 2026-09-30 23:55 UTC. It contains 144 CSV files and 1,031,380 rows. Files are monthly through August 2026 and weekly fragments for September 2026. All files share the same five-column schema:

```text
timestamp, open, high, low, close
```

There is no spread, tick-volume, MT5 server-time, or timezone column. Timestamps are 13-digit Unix epoch milliseconds. They decode cleanly as UTC and align with the 17:00 America/New_York daily open: 17:00 New York occurs at 22:00 UTC in winter (UTC-5) and 21:00 UTC in US summer (UTC-4). Example: 2015-01-01 22:00 UTC = 2015-01-01 17:00 EST = 2015-01-02 03:30 IST; 2026-09-28 21:00 UTC = 2026-09-28 17:00 EDT. The engine will use timezone-aware `America/New_York` and `Asia/Kolkata` conversions, never fixed offsets.

## Counts and coverage

| Item | Result |
|---|---:|
| CSV files | 144 |
| Total rows | 1,031,380 |
| Earliest timestamp | 2015-01-01 00:00:00 UTC |
| Latest timestamp | 2026-09-30 23:55:00 UTC |
| Expected bar interval | 5 minutes |
| Duplicate timestamps | 0 |
| Non-monotonic rows within files | 0 |
| Parse errors | 0 |
| Gaps of 6–30 minutes | 0 |
| Gaps greater than 5 minutes | 624 |
| Non-weekend/non-session gaps >5 minutes | 10 holiday/data-closure intervals |

The dominant time delta is exactly five minutes (1,030,755 transitions). The 624 larger gaps are overwhelmingly normal market closures/weekends. The ten remaining calendar gaps occur around holidays or short data closures, including Christmas Eve/Christmas and New Year’s Eve/New Year’s, plus one October 2024 closure. They are retained and will not be filled or interpolated.

| UTC year | Bars |
|---:|---:|
| 2015 | 87,726 |
| 2016 | 87,585 |
| 2017 | 87,297 |
| 2018 | 88,074 |
| 2019 | 88,067 |
| 2020 | 88,050 |
| 2021 | 87,585 |
| 2022 | 87,585 |
| 2023 | 87,285 |
| 2024 | 88,364 |
| 2025 | 88,038 |
| 2026 | 65,724 |

## OHLC validation

No rows violate any of the following checks:

- `high < low`: 0
- `open` outside `[low, high]`: 0
- `close` outside `[low, high]`: 0

Observed price ranges are approximately open 1046.799–5587.925, high 1048.041–5596.805, low 1046.231–5581.385, and close 1046.800–5587.628.

## Costs and unavailable modules

Because there is no spread column, the fixed spread fallback from the specification will be used: **$0.30 per ounce by default**, with `$0.20`, `$0.50`, 1.5× and 2× stress cases. Commission defaults to `$0` and the specified `$7` round-turn lot stress case will be included. No XAGUSD, DXY/EURUSD, economic-calendar, or other-instrument files are present, so SMT divergence and news-blackout variants will be skipped and explicitly reported as unavailable.

## Data-handling decisions

1. Raw CSVs remain immutable.
2. The loader will recursively discover all CSVs, concatenate in timestamp order, de-duplicate by UTC timestamp, and cache normalized data to Parquet when the optional Parquet engine is installed; otherwise it will use a documented CSV/NumPy fallback.
3. All higher-timeframe bars will be aligned to the 17:00 New York daily open. A higher-timeframe bar is usable only after its close timestamp.
4. The data ends on 2026-09-30 UTC, although the requested final filename range ends 2026-10-01; no post-2026-09-30 bars were found or invented.
