"""Evidence-aware search-basket diversification, NOT investable capital weights.
Uses aligned cumulative-PnL intervals, raw abs-correlation redundancy checks,
Ledoit-Wolf shrunk correlation for conditional residual novelty, and dataset caps.
All measures are in-sample diagnostics; missing evidence is never independence.
"""
from __future__ import annotations
import math
import numpy as np
from sklearn.covariance import LedoitWolf
from forge2_statistics import daily_changes
from forge2_expression import field_tokens


def dataset_members(expression,metadata):
    return sorted({metadata[t]['dataset'] for t in field_tokens(expression)
                   if t in metadata and metadata[t].get('type')!='GROUP' and metadata[t].get('dataset')})


def residual_fraction(raw,shrunk,i,ids,ridge):
    """Residual variance on RAW training covariance with shrunk-ridge coefficients.
    The ridge Schur shortcut and injected identity are not measured novelty.
    """
    if not ids:return 1.0
    coefficients=np.linalg.solve(shrunk[np.ix_(ids,ids)]+ridge*np.eye(len(ids)),shrunk[i,ids])
    value=1-2*coefficients@raw[i,ids]+coefficients@raw[np.ix_(ids,ids)]@coefficients
    if not np.isfinite(value) or value < -1e-8:raise ValueError('Invalid residual variance')
    return max(0.0,float(value))

def raw_subspace_fraction(x,i,ids,tolerance=1e-10):
    if not ids:return 1.0
    coefficients=np.linalg.lstsq(x[:,ids],x[:,i],rcond=tolerance)[0]
    return float(np.mean((x[:,i]-x[:,ids]@coefficients)**2)/np.mean(x[:,i]**2))

def select_basket(ordered,series_by_id,metadata,size,min_overlap=60,max_abs_correlation=.8,
                  min_residual_fraction=.1,max_dataset_fraction=.4,explore_fraction=.2,ridge=1e-6):
    ordered=list(ordered)
    if size<1 or min_overlap<10 or not 0<max_abs_correlation<1 or not 0<=min_residual_fraction<=1 or not 0<max_dataset_fraction<=1 or not 0<=explore_fraction<1 or ridge<=0:
        raise ValueError('Invalid basket constraints')
    report={'metric':'search_basket_diversity','selected':[],'verified':[],'exploration':[],
            'rejections':{},'common_intervals':0,'shrinkage':None,'reason':None,
            'caveat':'Standardized PnL interval diagnostics, not capital weights or independent bets; thresholds are engineering controls, not significance tests'}
    # This module refuses cross-universe pooling. Engine passes one primary
    # universe basket; the offline reviewer groups regimes explicitly.
    regimes={(r.get('region'),r.get('delay'),r.get('universe')) for r in ordered}
    if len(regimes)>1:raise ValueError('Basket must have one region/delay/universe regime')
    diffs={r['alpha_id']:daily_changes(series_by_id[r['alpha_id']]) for r in ordered
           if r.get('alpha_id') in series_by_id}
    eligible=[r for r in ordered if len(diffs.get(r.get('alpha_id'),{}))>=min_overlap]
    common=sorted(set.intersection(*(set(diffs[r['alpha_id']]) for r in eligible))) if eligible else []
    report['common_intervals']=len(common)
    if len(eligible)<2 or len(common)<min_overlap:
        report['reason']='insufficient_common_evidence; base ranking retained, diversity unverified'
        report['exploration']=[r.get('alpha_id') for r in ordered[:size]]
        report['selected']=report['exploration'][:]
        return ordered[:size],report
    x=np.column_stack([[diffs[r['alpha_id']][d] for d in common] for r in eligible])
    sd=x.std(axis=0);keep=np.flatnonzero(sd>1e-12)
    eligible=[eligible[i] for i in keep];x=x[:,keep]
    if len(eligible)<2:
        report['reason']='flat_series; base ranking retained, diversity unverified'
        report['exploration']=[r.get('alpha_id') for r in ordered[:size]];report['selected']=report['exploration'][:]
        return ordered[:size],report
    x=(x-x.mean(axis=0))/x.std(axis=0)
    raw=np.corrcoef(x,rowvar=False);estimate=LedoitWolf().fit(x);cov=estimate.covariance_
    diagonal=np.sqrt(np.diag(cov));shrunk=cov/np.outer(diagonal,diagonal)
    report['shrinkage']=float(estimate.shrinkage_)
    indices={r['alpha_id']:i for i,r in enumerate(eligible)}
    reserve=min(size-1,math.ceil(size*explore_fraction));core_target=size-reserve
    family_cap=max(1,math.ceil(size*max_dataset_fraction));counts={};selected=[];ids=[]
    for r in eligible:
        aid=r['alpha_id'];i=indices[aid];families=dataset_members(r['expression'],metadata)
        if not families:
            report['rejections'][aid]='unknown_dataset_attribution';continue
        if any(counts.get(f,0)>=family_cap for f in families):
            report['rejections'][aid]='dataset_budget';continue
        if ids and max(abs(raw[i,j]) for j in ids)>max_abs_correlation:
            report['rejections'][aid]='absolute_return_redundancy';continue
        raw_residual=raw_subspace_fraction(x,i,ids)
        if raw_residual<max(1e-10,min_residual_fraction):
            report['rejections'][aid]='raw_linear_subspace_redundancy';continue
        residual=1.0
        if ids:
            residual=residual_fraction(raw,shrunk,i,ids,ridge)
        if residual<min_residual_fraction:
            report['rejections'][aid]='low_conditional_residual_novelty';continue
        report['verified'].append({'alpha_id':aid,'residual_fraction':residual,'datasets':families,'raw_subspace_fraction':raw_residual})
        selected.append(r);ids.append(i)
        for f in families:counts[f]=counts.get(f,0)+1
        if len(selected)>=core_target:break
    # Explicit exploration reserve may have unknown return evidence, but never
    # includes a known duplicate or a known budget violation. It is not labeled
    # verified diversity and does not alter any platform qualification gate.
    chosen={r['alpha_id'] for r in selected}
    for r in ordered:
        aid=r.get('alpha_id')
        if aid in chosen or aid in report['rejections']:continue
        families=dataset_members(r['expression'],metadata)
        if families and any(counts.get(f,0)>=family_cap for f in families):continue
        if aid in indices and ids:
            i=indices[aid]
            if max(abs(raw[i,j]) for j in ids)>max_abs_correlation:continue
            if raw_subspace_fraction(x,i,ids)<max(1e-10,min_residual_fraction):continue
            residual=residual_fraction(raw,shrunk,i,ids,ridge)
            if residual<min_residual_fraction:continue
        if len(report['exploration'])>=reserve:break
        selected.append(r);chosen.add(aid);report['exploration'].append(aid)
        if aid in indices:ids.append(indices[aid])
        for f in families:counts[f]=counts.get(f,0)+1
    report['selected']=[r.get('alpha_id') for r in selected]
    report['dataset_counts']=counts
    report['reason']='measured_core_plus_explicit_exploration'
    return selected,report
