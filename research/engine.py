from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from data_loader import load_normalized
from resample import resample_all

_PREP_CACHE = {}
_POI_CACHE = {}
_EVENT_CACHE = {}

def _epoch_ns(series: pd.Series) -> np.ndarray:
    return pd.to_datetime(series, utc=True).dt.as_unit("ns").array.asi8


@dataclass
class EngineParams:
    swing_n: int = 2
    allow_buys: bool = True
    allow_sells: bool = True
    rr: float = 3.0
    pending_bars: int = 48
    spread_fraction: float = 0.000075
    spread_multiplier: float = 1.0
    buffer_atr_fraction: float = 0.15
    min_stop_atr_fraction: float = 0.50
    stop_cap_atr_multiple: float = 5.0
    gap_filter_atr_multiple: float = 1.0
    dollar_mode: bool = False
    dollar_buffer: float = 0.30
    dollar_min_stop: float = 1.50
    dollar_stop_cap: float = 25.0
    dollar_gap_filter: float = 5.0


def atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = bars.close.shift(1)
    tr = pd.concat([bars.high - bars.low, (bars.high - prev).abs(), (bars.low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def confirmed_swings(h4: pd.DataFrame, n: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    highs, lows = [], []
    h = h4.high.to_numpy(); lo = h4.low.to_numpy()
    for i in range(n, len(h4) - n):
        if h[i] >= h[i-n:i].max() and h[i] > h[i+1:i+n+1].max():
            highs.append({"pivot": i, "confirm": i+n, "time": h4.timestamp.iloc[i], "confirm_time": h4.close_time.iloc[i+n], "price": h[i]})
        if lo[i] <= lo[i-n:i].min() and lo[i] < lo[i+1:i+n+1].min():
            lows.append({"pivot": i, "confirm": i+n, "time": h4.timestamp.iloc[i], "confirm_time": h4.close_time.iloc[i+n], "price": lo[i]})
    return pd.DataFrame(highs), pd.DataFrame(lows)


def _bias_at(t, highs, lows):
    hs = highs[highs.confirm_time <= t].tail(2)
    ls = lows[lows.confirm_time <= t].tail(2)
    sell = len(hs) == 2 and len(ls) == 2 and hs.price.iloc[1] < hs.price.iloc[0] and ls.price.iloc[1] < ls.price.iloc[0]
    buy = len(hs) == 2 and len(ls) == 2 and hs.price.iloc[1] > hs.price.iloc[0] and ls.price.iloc[1] > ls.price.iloc[0]
    return ("sell" if sell else "") + ("buy" if buy else "")


def _fvg_or_ob(m30: pd.DataFrame, start, side: str):
    x = m30[(m30.close_time > start)].copy()
    if len(x) < 3: return None
    for i in range(2, len(x)):
        a, b, c = x.iloc[i-2], x.iloc[i-1], x.iloc[i]
        if side == "sell":
            if a.low > c.high: return {"type":"bearish_fvg", "tf":"M30", "zone_low":c.high, "zone_high":a.low, "formed":c.close_time}
            if b.close > b.open and c.close < c.open and c.open < b.low:
                lo, hi = min(b.open,b.close), max(b.open,b.close)
                return {"type":"bearish_ob", "tf":"M30", "zone_low":lo, "zone_high":hi, "formed":c.close_time}
        else:
            if a.high < c.low: return {"type":"bullish_fvg", "tf":"M30", "zone_low":a.high, "zone_high":c.low, "formed":c.close_time}
            if b.close < b.open and c.close > c.open and c.open > b.high:
                lo, hi = min(b.open,b.close), max(b.open,b.close)
                return {"type":"bullish_ob", "tf":"M30", "zone_low":lo, "zone_high":hi, "formed":c.close_time}
    return None


def _precompute_pois(m30: pd.DataFrame, side: str):
    op, hi, lo, cl = (m30[c].to_numpy() for c in ["open","high","low","close"])
    formed = m30.close_time.to_numpy()
    out=[]
    if side == "sell":
        fvg = np.flatnonzero(lo[:-2] > hi[2:]) + 2
        ob = np.flatnonzero((cl[1:-1] > op[1:-1]) & (cl[2:] < op[2:]) & (op[2:] < lo[1:-1])) + 2
        for i in sorted(set(fvg.tolist()+ob.tolist())):
            if i in set(fvg.tolist()): out.append({"type":"bearish_fvg","tf":"M30","zone_low":float(hi[i]),"zone_high":float(lo[i-2]),"formed":formed[i]})
            else: out.append({"type":"bearish_ob","tf":"M30","zone_low":float(min(op[i-1],cl[i-1])),"zone_high":float(max(op[i-1],cl[i-1])),"formed":formed[i]})
    else:
        fvg = np.flatnonzero(hi[:-2] < lo[2:]) + 2
        ob = np.flatnonzero((cl[1:-1] < op[1:-1]) & (cl[2:] > op[2:]) & (op[2:] > hi[1:-1])) + 2
        fset=set(fvg.tolist())
        for i in sorted(fset.union(ob.tolist())):
            if i in fset: out.append({"type":"bullish_fvg","tf":"M30","zone_low":float(hi[i-2]),"zone_high":float(lo[i]),"formed":formed[i]})
            else: out.append({"type":"bullish_ob","tf":"M30","zone_low":float(min(op[i-1],cl[i-1])),"zone_high":float(max(op[i-1],cl[i-1])),"formed":formed[i]})
    return out


def _make_levels(h4, swings, side):
    out=[]
    for _, s in swings.iterrows():
        p=int(s.pivot); confirm=int(s.confirm)
        if side == "sell":
            after=h4.iloc[p+1:]
            z=after[after.close < after.open].head(1)
        else:
            after=h4.iloc[p+1:]
            z=after[after.close > after.open].head(1)
        if z.empty: continue
        r=z.iloc[0]
        out.append({"side":side,"swing_time":s.time,"swing_price":s.price,"level":float(r.open),"level_time":r.timestamp,"confirm_time":r.close_time})
    return pd.DataFrame(out)


def _sweeps(h1, levels, side):
    out=[]
    ts = _epoch_ns(h1.close_time)
    highs = h1.high.to_numpy(); lows = h1.low.to_numpy(); closes = h1.close.to_numpy(); atrs = h1.atr.to_numpy()
    for _, lev in levels.iterrows():
        start = int(np.searchsorted(ts, pd.Timestamp(lev.confirm_time).value, side="right"))
        if start >= len(ts): continue
        mask = highs[start:] > lev.level if side == "sell" else lows[start:] < lev.level
        hits = np.flatnonzero(mask)
        if len(hits) == 0: continue
        j = start + int(hits[0])
        valid = closes[j] < lev.level if side == "sell" else closes[j] > lev.level
        if valid:
            sweep_high = highs[j] if side == "sell" else lows[j]
            out.append({**lev.to_dict(),"sweep_time":pd.Timestamp(ts[j], unit="ns", tz="UTC"),"sweep_high":float(sweep_high),"sweep_idx":j,"sweep_atr":float(atrs[j]) if np.isfinite(atrs[j]) else np.nan})
    return pd.DataFrame(out)


def _side_trades(m5, m30, sweeps, side, p: EngineParams):
    trades=[]
    m5_ts = _epoch_ns(m5.timestamp)
    m5_close = m5.close.to_numpy()
    m5_open = m5.open.to_numpy()
    m5_high = m5.high.to_numpy()
    m5_low = m5.low.to_numpy()
    m5_atr = m5.atr.to_numpy()
    m5_ist = m5.ist_time.to_numpy()
    m5_ny = m5.ny_time.to_numpy()
    m5_gap = m5.gap_minutes.to_numpy()
    poi_key = (id(m30), side)
    if poi_key not in _POI_CACHE:
        _POI_CACHE[poi_key] = _precompute_pois(m30, side)
    pois = _POI_CACHE[poi_key]
    poi_times = np.array([pd.Timestamp(x["formed"]).value for x in pois], dtype="int64")
    for _, sw in sweeps.iterrows():
        pos = int(np.searchsorted(poi_times, pd.Timestamp(sw.sweep_time).value, side="right"))
        poi=pois[pos] if pos < len(pois) else None
        if poi is None: continue
        entry=(poi["zone_low"]+poi["zone_high"])/2
        sweep_pos = int(np.searchsorted(m5_ts, pd.Timestamp(sw.sweep_time).value, side="right") - 1)
        if sweep_pos < 0: continue
        sweep_atr=sw.sweep_atr if np.isfinite(sw.sweep_atr) else float(m5_atr[sweep_pos])
        h1_atr=sweep_atr
        spread=float(m5_close[min(sweep_pos+1, len(m5_close)-1)] * p.spread_fraction * p.spread_multiplier)
        buffer = p.dollar_buffer if p.dollar_mode else p.buffer_atr_fraction*h1_atr
        stop = sw.sweep_high + buffer + spread if side=="sell" else sw.sweep_high - buffer - spread
        risk=abs(stop-entry)
        minstop=p.dollar_min_stop if p.dollar_mode else p.min_stop_atr_fraction*h1_atr
        cap=p.dollar_stop_cap if p.dollar_mode else p.stop_cap_atr_multiple*h1_atr
        if risk < minstop or risk > cap: continue
        target=entry - p.rr*risk if side=="sell" else entry + p.rr*risk
        start = int(np.searchsorted(m5_ts, pd.Timestamp(poi["formed"]).value, side="right"))
        end = min(start + p.pending_bars + 1, len(m5))
        fill_i=None; fill=None; exit_idx=None; reason=None
        for j in range(start, end):
            b_close, b_open, b_high, b_low = m5_close[j], m5_open[j], m5_high[j], m5_low[j]
            # cancel on sweep invalidation and entry gap filter
            if side=="sell" and b_close > sw.sweep_high: break
            if side=="buy" and b_close < sw.sweep_high: break
            if fill_i is None:
                prev_close = m5_close[j-1] if j > 0 else b_open
                gap = abs(b_open-prev_close)
                threshold = p.dollar_gap_filter if p.dollar_mode else p.gap_filter_atr_multiple*float(m5_atr[j])
                if gap > threshold: continue
                reaches = b_high >= entry if side=="sell" else b_low <= entry
                if reaches:
                    fill_i=j; fill=True
                    continue
            else:
                stop_hit = (b_high + spread >= stop) if side=="sell" else (b_low - spread <= stop)
                target_hit = (b_low + spread <= target) if side=="sell" else (b_high - spread >= target)
                if stop_hit:
                    exit_idx=j; reason="stop"; break
                if target_hit:
                    exit_idx=j; reason="target"; break
        if fill is None or exit_idx is None: continue
        fill_price=entry
        exit_price=stop if reason=="stop" else target
        # R after entry/exit spread effect; stop/target already include spread
        r=((fill_price-exit_price)/risk) if side=="sell" else ((exit_price-fill_price)/risk)
        fill_ts = pd.Timestamp(m5_ts[fill_i], unit="ns", tz="UTC")
        exit_ts = pd.Timestamp(m5_ts[exit_idx], unit="ns", tz="UTC")
        trades.append({"side":side,"level_time":lev_time(sw["level_time"]),"situation":"A","sweep_time":sw["sweep_time"],"sweep_high":sw["sweep_high"],"poi_type":poi["type"],"poi_timeframe":"M30","order_time":pd.Timestamp(poi["formed"]),"entry":entry,"stop":stop,"target":target,"fill_time":fill_ts,"exit_time":exit_ts,"exit_reason":reason,"r_result":r,"entry_ist":m5_ist[fill_i],"entry_new_york":m5_ny[fill_i],"year":fill_ts.year,"holding_minutes":(exit_ts-fill_ts).total_seconds()/60,"spread":spread})
    return pd.DataFrame(trades)


def lev_time(x): return x


def run_baseline(root: Path, p: EngineParams | None=None):
    p=p or EngineParams()
    cache_key = str(root.resolve())
    if cache_key not in _PREP_CACHE:
        m5=load_normalized(root)
        m5["atr"]=atr(m5)
        bars=resample_all(m5)
        _PREP_CACHE[cache_key] = (m5, bars)
    m5, bars = _PREP_CACHE[cache_key]
    event_key=(cache_key,p.swing_n)
    if event_key not in _EVENT_CACHE:
        h1=bars["H1"].copy(); h4=bars["H4"].copy(); h1["atr"]=atr(h1); h4["atr"]=atr(h4)
        hs,ls=confirmed_swings(h4,p.swing_n)
        event_data={"h1":h1,"h4":h4,"sell":_sweeps(h1,_make_levels(h4,hs,"sell"),"sell"),"buy":_sweeps(h1,_make_levels(h4,ls,"buy"),"buy")}
        _EVENT_CACHE[event_key]=event_data
    event_data=_EVENT_CACHE[event_key]
    h1,h4=event_data["h1"],event_data["h4"]
    m30=bars["M30"]
    result=[]
    sides = []
    if p.allow_sells: sides.append("sell")
    if p.allow_buys: sides.append("buy")
    for side in sides:
        sweeps=event_data[side]
        if not sweeps.empty:
            result.append(_side_trades(m5, m30, sweeps, side, p))
    trades=pd.concat(result,ignore_index=True) if result else pd.DataFrame()
    if not trades.empty:
        trades=trades.sort_values(["order_time","fill_time"]).reset_index(drop=True)
        kept=[]; last_exit=None
        for _, tr in trades.iterrows():
            if last_exit is None or tr.order_time > last_exit:
                kept.append(tr); last_exit=tr.exit_time
        trades=pd.DataFrame(kept).sort_values("fill_time").reset_index(drop=True) if kept else pd.DataFrame()
    return trades


def metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["scope","year","trades","win_rate","avg_win_r","avg_loss_r","expectancy_r","profit_factor","total_r","avg_holding_min"])
    rows=[]
    for key, g in [("combined",trades)]+[(x,trades[trades.side==x]) for x in ["buy","sell"]]:
        if g.empty: continue
        wins=g[g.r_result>0].r_result; losses=g[g.r_result<=0].r_result
        rows.append({"scope":key,"year":"all","trades":len(g),"win_rate":float((g.r_result>0).mean()),"avg_win_r":float(wins.mean()) if len(wins) else 0,"avg_loss_r":float(losses.mean()) if len(losses) else 0,"expectancy_r":float(g.r_result.mean()),"profit_factor":float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else np.inf,"total_r":float(g.r_result.sum()),"avg_holding_min":float(g.holding_minutes.mean())})
        for y, gy in g.groupby("year"):
            wins=gy[gy.r_result>0].r_result; losses=gy[gy.r_result<=0].r_result
            rows.append({"scope":key,"year":int(y),"trades":len(gy),"win_rate":float((gy.r_result>0).mean()),"avg_win_r":float(wins.mean()) if len(wins) else 0,"avg_loss_r":float(losses.mean()) if len(losses) else 0,"expectancy_r":float(gy.r_result.mean()),"profit_factor":float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else np.inf,"total_r":float(gy.r_result.sum()),"avg_holding_min":float(gy.holding_minutes.mean())})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    root=Path(__file__).resolve().parents[1]
    out=root/"research/results"; out.mkdir(parents=True,exist_ok=True)
    t=run_baseline(root); t.to_csv(out/"baseline_trade_log.csv",index=False); metrics(t).to_csv(out/"baseline_metrics.csv",index=False)
    print(metrics(t).to_string(index=False))
    print("trades",len(t))
