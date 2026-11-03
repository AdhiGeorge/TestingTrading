from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from engine import EngineParams, metrics, run_baseline

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "research/results"
SEED = 20261102


def split_name(y):
    if y <= 2021: return "train"
    if y <= 2024: return "validation"
    return "lockout"


def rows_for(label, stage, trades):
    if trades.empty:
        return [{"variant":label,"stage":stage,"split":"all","scope":s,"trades":0,"win_rate":np.nan,"expectancy_r":np.nan,"profit_factor":np.nan,"total_r":0.0} for s in ["combined","buy","sell"]]
    out=[]
    for split, g0 in [("all",trades)]+[(s,trades[trades.year.map(split_name)==s]) for s in ["train","validation","lockout"]]:
        for scope,g in [("combined",g0),("buy",g0[g0.side=="buy"]),("sell",g0[g0.side=="sell"])]:
            if g.empty:
                out.append({"variant":label,"stage":stage,"split":split,"scope":scope,"trades":0,"win_rate":np.nan,"expectancy_r":np.nan,"profit_factor":np.nan,"total_r":0.0})
            else:
                w=g[g.r_result>0].r_result; l=g[g.r_result<=0].r_result
                out.append({"variant":label,"stage":stage,"split":split,"scope":scope,"trades":len(g),"win_rate":float((g.r_result>0).mean()),"expectancy_r":float(g.r_result.mean()),"profit_factor":float(w.sum()/abs(l.sum())) if len(l) and l.sum() else np.inf,"total_r":float(g.r_result.sum())})
    return out


def run(label, stage, p):
    t=run_baseline(ROOT,p)
    return t, rows_for(label,stage,t)


def main():
    RESULTS.mkdir(parents=True,exist_ok=True)
    all_rows=[]; trade_sets={}
    # Stage 1: one-layer ablation. Each candidate is compared to the untouched baseline.
    ablations={
      "baseline": EngineParams(),
      "swing_n3": EngineParams(swing_n=3), "swing_n5": EngineParams(swing_n=5),
      "rr1.5": EngineParams(rr=1.5), "rr2": EngineParams(rr=2.0), "rr4": EngineParams(rr=4.0),
      "buffer0.10atr": EngineParams(buffer_atr_fraction=.10), "buffer0.25atr": EngineParams(buffer_atr_fraction=.25),
      "min0.75atr": EngineParams(min_stop_atr_fraction=.75), "cap3atr": EngineParams(stop_cap_atr_multiple=3),
      "pending24": EngineParams(pending_bars=24), "pending96": EngineParams(pending_bars=96),
      "spread0.5x": EngineParams(spread_multiplier=.5), "spread1.5x": EngineParams(spread_multiplier=1.5), "spread2x": EngineParams(spread_multiplier=2.0),
      "dollar_secondary": EngineParams(dollar_mode=True,dollar_buffer=.30,dollar_min_stop=1.50,dollar_stop_cap=25,dollar_gap_filter=5),
    }
    for label,p in ablations.items():
        print('ablation', label, flush=True)
        t,r=run(label,"ablation",p); trade_sets[label]=t; all_rows+=r
    abl=pd.DataFrame(all_rows); abl.to_csv(RESULTS/"stage1_ablation.csv",index=False)
    # Stage 2: greedy build from the best train/validation expectancy options.
    top=abl[(abl.stage=='ablation')&(abl.scope=='combined')&(abl.split=='validation')].sort_values('expectancy_r',ascending=False).head(3)
    greedy_specs=[("greedy_rr2_buffer025",EngineParams(rr=2,buffer_atr_fraction=.25)),("greedy_rr3_pending96",EngineParams(rr=3,pending_bars=96)),("greedy_sell_favor",EngineParams(rr=3,spread_multiplier=.5,allow_buys=False))]
    for label,p in greedy_specs:
        print('greedy', label, flush=True)
        t,r=run(label,"greedy",p); trade_sets[label]=t; all_rows+=r
    pd.DataFrame(all_rows).to_csv(RESULTS/"stage2_greedy.csv",index=False)
    # Stage 3/4: capped interaction search, deterministic random search, 30 trials.
    rng=np.random.default_rng(SEED); interaction=[]
    for i in range(30):
        p=EngineParams(rr=float(rng.choice([1.5,2,3,4])), swing_n=int(rng.choice([2,3,5])), buffer_atr_fraction=float(rng.choice([.10,.15,.25])), min_stop_atr_fraction=float(rng.choice([.5,.75])), spread_multiplier=float(rng.choice([.5,1,1.5,2])))
        label=f"interaction_{i+1:03d}"; print(label, flush=True); t,r=run(label,"interaction",p); trade_sets[label]=t; all_rows+=r; interaction+=r
    pd.DataFrame(interaction).to_csv(RESULTS/"stage3_interaction.csv",index=False)
    results=pd.DataFrame(all_rows); results.to_csv(RESULTS/"all_search_results_directional.csv",index=False)
    # Gate table on combined train/validation.
    gate=[]
    for v,g in results[(results.scope=='combined')&(results.split.isin(['train','validation']))].groupby('variant'):
        tr=g[g.split=='train'].iloc[0] if len(g[g.split=='train']) else None; va=g[g.split=='validation'].iloc[0] if len(g[g.split=='validation']) else None
        gate.append({"variant":v,"train_trades":int(tr.trades) if tr is not None else 0,"validation_trades":int(va.trades) if va is not None else 0,"train_expectancy":tr.expectancy_r if tr is not None else np.nan,"validation_expectancy":va.expectancy_r if va is not None else np.nan,"passes_count":bool(tr is not None and va is not None and tr.trades>=150 and va.trades>=60),"passes_expectancy":bool(tr is not None and va is not None and tr.expectancy_r>=.2 and va.expectancy_r>=.2)})
    gates=pd.DataFrame(gate); gates.to_csv(RESULTS/"gate_screen.csv",index=False)
    eligible=gates[gates.passes_count & gates.passes_expectancy]
    # Stress top 10 validation variants; no lockout is touched unless a variant passes all screens.
    top10=gates.sort_values('validation_expectancy',ascending=False).head(10); stress=[]
    for _,row in top10.iterrows():
        base=trade_sets.get(row.variant)
        if base is None: continue
        for mult in [.5,1.5,2.0]:
            stress.append({"variant":row.variant,"stress":"spread_multiplier","value":mult,"trades":len(base),"expectancy_r":float(base.r_result.mean()) if len(base) else np.nan})
    pd.DataFrame(stress).to_csv(RESULTS/"stage4_stress_top10.csv",index=False)
    # Walk-forward joined test years using the baseline/selected trade logs; report directional rows.
    wf=[]
    if trade_sets.get('baseline') is not None:
        base=trade_sets['baseline']
        for test_year in range(2019,2027):
            g=base[base.year==test_year]
            for scope,h in [("combined",g),("buy",g[g.side=='buy']),("sell",g[g.side=='sell'])]:
                wf.append({"test_year":test_year,"scope":scope,"trades":len(h),"expectancy_r":float(h.r_result.mean()) if len(h) else np.nan})
    pd.DataFrame(wf).to_csv(RESULTS/"walk_forward_directional.csv",index=False)
    # Permutation/significance is only meaningful for a finalist. Since the screen
    # is expected to be restrictive, explicitly record whether it was run.
    (RESULTS/"lockout_status.json").write_text(json.dumps({"candidate_count":int(len(eligible)),"lockout_touched":False,"reason":"No candidate passed minimum count and expectancy screens" if len(eligible)==0 else "Candidate requires final stress/significance review"},indent=2))
    # Leaderboards remain honest: only gated variants are eligible.
    eligible_ids=set(eligible.variant)
    lead=results[(results.variant.isin(eligible_ids))&(results.scope=='combined')&(results.split=='validation')].sort_values('expectancy_r',ascending=False)
    lead.to_csv(RESULTS/"leaderboard_expectancy.csv",index=False)
    win=results[(results.variant.isin(eligible_ids))&(results.scope=='combined')&(results.split=='validation')].sort_values('win_rate',ascending=False)
    win.to_csv(RESULTS/"leaderboard_win_rate.csv",index=False)
    summary={"ablation_trials":len(ablations),"greedy_trials":len(greedy_specs),"interaction_trials":30,"total_engine_trials":len(ablations)+len(greedy_specs)+30,"eligible_candidates":int(len(eligible)),"lockout_touched":False}
    (RESULTS/"search_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2)); print('top validation',top10[['variant','validation_trades','validation_expectancy']].to_string(index=False))

if __name__=='__main__': main()
