"""Spectral effective rank of ALIGNED daily PnL changes—not portfolio ENB.
No overlap => unknown, never zero correlation. Complete-case covariance is PSD.
"""
from __future__ import annotations
import datetime
import math


def daily_changes(series, max_gap_days=4):
    points=[]
    for date,value in sorted(series.items()):
        try:
            day=datetime.date.fromisoformat(str(date)[:10]);value=float(value)
            if math.isfinite(value):points.append((day,str(date),value))
        except (ValueError,TypeError):continue
    return {(d1,d2):v2-v1 for (day1,d1,v1),(day2,d2,v2) in zip(points,points[1:])
            if 0 < (day2-day1).days <= max_gap_days}


def diversification_diagnostics(series_by_id, min_overlap=60):
    import numpy as np
    diffs={k:daily_changes(v) for k,v in series_by_id.items()}
    eligible={k:v for k,v in diffs.items() if len(v)>=min_overlap}
    out={'metric':'spectral_effective_rank','value':None,'input_series':len(diffs),
         'eligible_series':len(eligible),'common_dates':0,'common_intervals':0,
         'observation_unit':'matched cumulative-PnL intervals; not guaranteed single trading days','reason':None}
    if len(eligible)<2:
        out['reason']='insufficient_series';return out
    common=sorted(set.intersection(*(set(v) for v in eligible.values())))
    out['common_dates']=len(common) # compatibility alias
    out['common_intervals']=len(common)
    if len(common)<min_overlap:
        out['reason']='insufficient_common_overlap';return out
    x=np.array([[v[d] for d in common] for v in eligible.values()],dtype=float)
    if np.any(x.std(axis=1)<=1e-12):
        out['reason']='flat_series';return out
    corr=np.corrcoef(x)
    values=np.linalg.eigvalsh(corr)
    if values.min() < -1e-8:
        out['reason']='non_psd_correlation';return out
    values=np.maximum(values,0.0);weights=values/values.sum();weights=weights[weights>1e-12]
    out['value']=float(np.exp(-(weights*np.log(weights)).sum()))
    return out
