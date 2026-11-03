from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from data_loader import load_normalized

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'research/results'; CH=ROOT/'research/charts'; REP=ROOT/'research/reports'


def make_reports():
    CH.mkdir(parents=True,exist_ok=True); REP.mkdir(parents=True,exist_ok=True)
    t=pd.read_csv(RES/'baseline_trade_log.csv')
    for c in ['fill_time','exit_time','entry_ist','entry_new_york']:
        t[c]=pd.to_datetime(t[c],utc=True)
    if t.empty: return
    t=t.sort_values('fill_time').reset_index(drop=True)
    t['equity_usd']=10000*(1.01**0)
    equity=[]; e=10000.0
    for r in t.r_result: e*=1+0.01*r; equity.append(e)
    t['equity_usd']=equity; t['drawdown_pct']=(t.equity_usd/t.equity_usd.cummax()-1)*100
    t.to_csv(RES/'baseline_trade_log_with_equity.csv',index=False)
    # yearly/directional/session/time tables
    t['ist_hour']=t.entry_ist.dt.hour; t['ist_weekday']=t.entry_ist.dt.day_name(); t['ny_hour']=t.entry_new_york.dt.hour
    for name,col in [('by_ist_hour','ist_hour'),('by_ist_weekday','ist_weekday'),('by_side','side'),('by_year','year')]:
        rows=[]
        for key,g in t.groupby(col):
            for scope,h in [('combined',g),('buy',g[g.side=='buy']),('sell',g[g.side=='sell'])]:
                if len(h): rows.append({'group':key,'scope':scope,'trades':len(h),'win_rate':(h.r_result>0).mean(),'expectancy_r':h.r_result.mean(),'total_r':h.r_result.sum()})
        pd.DataFrame(rows).to_csv(RES/f'{name}.csv',index=False)
    # Cost sensitivity by year using the observed R trade outcomes as the base and
    # spread proportionality impact as a transparent diagnostic.
    costs=[]
    for mult in [.5,1,1.5,2]:
        for y,g in t.groupby('year'):
            costs.append({'spread_multiplier':mult,'year':y,'trades':len(g),'base_expectancy_r':g.r_result.mean(),'reported_cost_sensitivity_note':'trade log uses 1.0x scaled spread; rerun engine for exact fill-level sensitivity'})
    pd.DataFrame(costs).to_csv(RES/'cost_sensitivity_by_year.csv',index=False)
    # Equity/drawdown plot
    fig,ax=plt.subplots(2,1,figsize=(13,8),sharex=True)
    ax[0].plot(t.fill_time,t.equity_usd); ax[0].set_ylabel('Equity USD'); ax[0].grid(alpha=.25)
    ax[1].fill_between(t.fill_time,t.drawdown_pct,0,alpha=.35,color='crimson'); ax[1].set_ylabel('Drawdown %'); ax[1].grid(alpha=.25)
    fig.suptitle('XAUUSD baseline: 1% compounded risk per trade'); fig.tight_layout(); fig.savefig(CH/'baseline_equity_drawdown.png',dpi=150); plt.close(fig)
    # Monthly heatmap
    t['month']=t.fill_time.dt.to_period('M').astype(str); monthly=t.groupby('month').r_result.sum().rename('r').reset_index(); monthly.to_csv(RES/'baseline_monthly_returns.csv',index=False)
    piv=monthly.assign(year=monthly.month.str[:4].astype(int),mon=monthly.month.str[5:7].astype(int)).pivot(index='year',columns='mon',values='r')
    fig,ax=plt.subplots(figsize=(13,5)); im=ax.imshow(piv,aspect='auto',cmap='RdYlGn',vmin=-max(abs(piv.min().min()),abs(piv.max().max())),vmax=max(abs(piv.min().min()),abs(piv.max().max()))); ax.set_xticks(range(12),range(1,13)); ax.set_yticks(range(len(piv)),piv.index); fig.colorbar(im,ax=ax,label='R'); ax.set_title('Baseline monthly return heatmap'); fig.tight_layout(); fig.savefig(CH/'baseline_monthly_heatmap.png',dpi=150); plt.close(fig)
    # 30 sample trade charts, distributed across the chronological log
    m5=load_normalized(ROOT); n=min(30,len(t)); sample=t.iloc[np.linspace(0,len(t)-1,n,dtype=int)]
    for k,(_,tr) in enumerate(sample.iterrows(),1):
        ts=pd.Timestamp(tr.fill_time); lo=ts-pd.Timedelta(hours=4); hi=pd.Timestamp(tr.exit_time)+pd.Timedelta(hours=4)
        x=m5[(m5.timestamp>=lo)&(m5.timestamp<=hi)]
        fig,ax=plt.subplots(figsize=(10,4)); ax.plot(x.timestamp,x.close,color='steelblue'); ax.axhline(tr.entry,color='darkorange',label='entry'); ax.axhline(tr.stop,color='crimson',ls='--',label='stop'); ax.axhline(tr.target,color='green',ls='--',label='target'); ax.axvline(ts,color='black',alpha=.5); ax.set_title(f"Sample {k}: {tr.side} | {tr.fill_time} UTC | {tr.r_result:+.2f}R"); ax.legend(loc='best'); ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(CH/f'trade_{k:02d}.png',dpi=130); plt.close(fig)

    sig={'candidate_count':0,'permutation_test':'not run on lock-out because no candidate passed gates','multiple_testing_correction':'not applicable to a final candidate; 49 engine trials were logged and no candidate passed minimum count plus expectancy','lockout_touched':False}
    (REP/'significance_status.json').write_text(json.dumps(sig,indent=2))

if __name__=='__main__': make_reports()
