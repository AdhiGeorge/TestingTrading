from __future__ import annotations

from pathlib import Path
import pandas as pd
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = "UTC"

TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def _bar_agg(x: pd.DataFrame) -> pd.Series:
    return pd.Series({
        "open": x.open.iloc[0], "high": x.high.max(), "low": x.low.min(),
        "close": x.close.iloc[-1], "volume": len(x),
        "start_time": x.timestamp.iloc[0], "close_time": x.timestamp.iloc[-1] + pd.Timedelta(minutes=5),
    })


def resample_aligned(m5: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "M5":
        out = m5[["timestamp", "open", "high", "low", "close"]].copy()
        out["close_time"] = out.timestamp + pd.Timedelta(minutes=5)
        return out
    if timeframe not in TF_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    mins = TF_MINUTES[timeframe]
    x = m5[["timestamp", "open", "high", "low", "close"]].copy()
    # Convert to NY for session identity; subtracting 17 hours makes the
    # session date boundary midnight at the 17:00 NY forex-day open. For H4
    # and intraday timeframes, bucket by minutes since that boundary.
    ny = x.timestamp.dt.tz_convert(NY)
    session_anchor = ny.dt.normalize() + pd.Timedelta(hours=17)
    session_anchor = session_anchor.where(ny >= session_anchor, session_anchor - pd.Timedelta(days=1))
    elapsed = ((ny - session_anchor).dt.total_seconds() // 60).astype("int64")
    bucket = (elapsed // mins) * mins
    x["_anchor"] = session_anchor
    x["_bucket"] = bucket
    out = x.groupby(["_anchor", "_bucket"], sort=True, group_keys=False).apply(_bar_agg, include_groups=False).reset_index()
    out["timestamp"] = out["start_time"]
    out["close_time"] = out["close_time"].dt.tz_convert("UTC")
    out["timestamp"] = out["timestamp"].dt.tz_convert("UTC")
    return out[["timestamp", "open", "high", "low", "close", "volume", "close_time"]].sort_values("timestamp").reset_index(drop=True)


def resample_all(m5: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {tf: resample_aligned(m5, tf) for tf in TF_MINUTES}


if __name__ == "__main__":
    from data_loader import load_normalized
    x = load_normalized(Path("."))
    for tf, bars in resample_all(x).items():
        print(tf, len(bars), bars.timestamp.min(), bars.timestamp.max(), bars.close_time.min(), bars.close_time.max())
