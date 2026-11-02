from __future__ import annotations

import csv
import datetime as dt
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
IST = ZoneInfo("Asia/Kolkata")


def discover_csvs(root: Path) -> list[Path]:
    return sorted(root.glob("**/xauusd-m5-bid-*.csv"))


def _read_one(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    # Source timestamps are verified 13-digit Unix milliseconds. Do not infer a
    # local timezone from the machine running the code.
    ts = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    out = df[["open", "high", "low", "close"]].copy()
    out.insert(0, "timestamp", ts)
    out["source_file"] = path.name
    return out


def load_normalized(root: Path) -> pd.DataFrame:
    files = discover_csvs(root)
    if not files:
        raise FileNotFoundError(f"No xauusd-m5-bid CSVs found under {root}")
    frames = [_read_one(p) for p in files]
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("timestamp", kind="mergesort")
    df = df.drop_duplicates("timestamp", keep="first").reset_index(drop=True)
    df["ny_time"] = df["timestamp"].dt.tz_convert(NY)
    df["ist_time"] = df["timestamp"].dt.tz_convert(IST)
    df["year"] = df["timestamp"].dt.year.astype("int16")
    df["gap_minutes"] = df["timestamp"].diff().dt.total_seconds().div(60).fillna(5.0)
    df["bar_minutes"] = 5
    return df


def quality_summary(df: pd.DataFrame) -> dict:
    gaps = df.loc[df["gap_minutes"] > 5, ["timestamp", "gap_minutes"]]
    flat = (df.open == df.high) & (df.high == df.low) & (df.low == df.close)
    ny_hour = df.ny_time.dt.hour
    low_liquidity = ny_hour.isin([17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5])
    flat_by_year = df.assign(_flat=flat, _low_liq=low_liquidity).groupby(df.timestamp.dt.year).agg(
        bars=("timestamp", "size"), flat_bars=("_flat", "sum"), low_liq_flat=("_flat", lambda x: int((x & low_liquidity.loc[x.index]).sum()))
    )
    flat_report = {
        str(y): {
            "bars": int(r.bars), "flat_bars": int(r.flat_bars),
            "share": float(r.flat_bars / r.bars),
            "flat_share_in_ny_17_06": float(r.low_liq_flat / r.flat_bars) if r.flat_bars else 0.0,
        } for y, r in flat_by_year.iterrows()
    }
    ohlc_bad = {
        "high_lt_low": int((df.high < df.low).sum()),
        "open_outside_range": int(((df.open < df.low) | (df.open > df.high)).sum()),
        "close_outside_range": int(((df.close < df.low) | (df.close > df.high)).sum()),
    }
    return {
        "rows": int(len(df)),
        "first_utc": df.timestamp.min().isoformat(),
        "last_utc": df.timestamp.max().isoformat(),
        "duplicates": int(df.timestamp.duplicated().sum()),
        "non_monotonic": int((df.timestamp.diff().dt.total_seconds() <= 0).fillna(False).sum()),
        "gaps_gt_5": int(len(gaps)),
        "gaps_6_to_30": int(((gaps.gap_minutes >= 6) & (gaps.gap_minutes <= 30)).sum()),
        "ohlc_anomalies": ohlc_bad,
        "bars_by_year": {str(k): int(v) for k, v in df.groupby(df.timestamp.dt.year).size().items()},
        "columns": list(df.columns),
        "has_spread": "spread" in df.columns,
        "flat_bars_total": int(flat.sum()),
        "flat_bars_share": float(flat.mean()),
        "flat_bars_by_year": flat_report,
        "sha256_source_manifest": source_manifest_hash(df),
    }


def source_manifest_hash(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for f in sorted(df.source_file.drop_duplicates()):
        h.update(f.encode())
    return h.hexdigest()


def write_cache(df: pd.DataFrame, cache_path: Path) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache_path, index=False)
    except ImportError:
        # A deterministic fallback keeps the pipeline usable before optional
        # parquet dependencies are installed; production runs should install
        # requirements.txt and use parquet.
        fallback = cache_path.with_suffix(".csv")
        df.to_csv(fallback, index=False)
        return fallback
    return cache_path


if __name__ == "__main__":
    import json
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    frame = load_normalized(root)
    print(json.dumps(quality_summary(frame), indent=2, default=str))
    print("cache:", write_cache(frame, root / "research/cache/xauusd_m5_normalized.parquet"))
