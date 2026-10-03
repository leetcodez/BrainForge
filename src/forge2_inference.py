"""Offline inference on explicit daily arithmetic excess RETURNS, not dollar PnL.
HAC delta-method Sharpe uncertainty and overlapping moving-block bootstrap.
Neither output corrects selection bias, proves stationarity, or replaces holdout.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.stats import norm


def _sample(values,min_observations=30):
    x=np.asarray(values,dtype=float)
    if x.ndim!=1 or len(x)<min_observations or not np.isfinite(x).all():
        raise ValueError('Need a finite 1D series with sufficient observations; missing rows cannot be silently dropped')
    sigma=float(x.std(ddof=0))
    if sigma<=1e-12:raise ValueError('Sharpe inference is undefined for a flat series')
    return x,float(x.mean()),sigma


def sharpe_inference(values,periods_per_year=252,lags=None,confidence=.95):
    x,mu,sigma=_sample(values)
    if not 0<confidence<1 or periods_per_year<=0:raise ValueError('Invalid confidence/annualization')
    n=len(x);sr=mu/sigma
    if lags is None:lags=int(math.floor(4*(n/100)**(2/9)))
    if type(lags) is not int or not 0<=lags<n:raise ValueError('Invalid HAC lag count')
    z=(x-mu)/sigma
    influence=z-.5*sr*(z*z-1)
    influence-=influence.mean()
    gamma0=float(influence@influence/n)
    lrv=gamma0+2*sum((1-k/(lags+1))*float(influence[k:]@influence[:-k]/n) for k in range(1,lags+1))
    if lrv < -1e-10:raise ValueError('Negative long-run variance')
    se=math.sqrt(max(lrv,0)/n);critical=float(norm.ppf((1+confidence)/2))
    scale=math.sqrt(periods_per_year)
    return {'metric':'hac_delta_method_sharpe','n':n,'lags':lags,'daily_sharpe':sr,
            'annualized_scaling_proxy':sr*scale,'daily_standard_error':se,
            'iid_standard_error':math.sqrt(gamma0/n),
            'daily_interval':[sr-critical*se,sr+critical*se],
            'annualized_scaling_interval':[(sr-critical*se)*scale,(sr+critical*se)*scale],
            'confidence':confidence,'unit':'daily arithmetic excess return',
            'caveat':'sqrt-time annualization is a scaling proxy under serial dependence; CI is asymptotic, conditional on chosen lag, not selection-adjusted'}


def moving_block_sharpe(values,block_length=None,resamples=1000,seed=20261002,confidence=.95):
    x,mu,sigma=_sample(values);n=len(x)
    if block_length is None:block_length=max(2,round(n**(1/3)))
    if type(block_length) is not int or not 1<=block_length<=n//4:raise ValueError('Block length must leave at least four blocks')
    if type(resamples) is not int or resamples<200 or not 0<confidence<1:raise ValueError('Need at least 200 resamples and valid confidence')
    rng=np.random.default_rng(seed);k=math.ceil(n/block_length)
    offsets=np.arange(block_length);estimates=[]
    for _ in range(resamples):
        starts=rng.integers(0,n-block_length+1,size=k)
        draw=x[(starts[:,None]+offsets).ravel()[:n]]
        sd=float(draw.std(ddof=0))
        if sd>1e-12:estimates.append(float(draw.mean()/sd))
    if len(estimates)<.95*resamples:raise ValueError('Too many degenerate bootstrap draws')
    tail=(1-confidence)/2
    return {'metric':'overlapping_moving_block_sharpe','daily_sharpe':mu/sigma,'n':n,
            'block_length':block_length,'resamples':resamples,'valid_draws':len(estimates),'seed':seed,
            'daily_percentile_interval':np.quantile(estimates,[tail,1-tail]).tolist(),
            'confidence':confidence,'caveat':'Dependent-data diagnostic under local stationarity; percentile coverage is approximate, block choice matters, not a multiple-testing correction'}


def paired_sharpe_inference(a,b,lags=None,confidence=.95):
    """HAC uncertainty of a paired daily Sharpe difference on the SAME rows."""
    a,ma,sa=_sample(a);b,mb,sb=_sample(b)
    if len(a)!=len(b):raise ValueError('Paired returns must share identical aligned observations')
    if not 0<confidence<1:raise ValueError('Invalid confidence')
    n=len(a);sr_a=ma/sa;sr_b=mb/sb
    if lags is None:lags=int(math.floor(4*(n/100)**(2/9)))
    if type(lags) is not int or not 0<=lags<n:raise ValueError('Invalid HAC lag count')
    za=(a-ma)/sa;zb=(b-mb)/sb
    psi=(za-.5*sr_a*(za*za-1))-(zb-.5*sr_b*(zb*zb-1));psi-=psi.mean()
    lrv=float(psi@psi/n)+2*sum((1-k/(lags+1))*float(psi[k:]@psi[:-k]/n) for k in range(1,lags+1))
    if lrv < -1e-10:raise ValueError('Negative paired long-run variance')
    se=math.sqrt(max(0,lrv)/n);difference=sr_a-sr_b;z=float(norm.ppf((1+confidence)/2))
    return {'metric':'paired_conditional_hac_sharpe_difference','daily_difference':difference,'standard_error':se,
            'interval':[difference-z*se,difference+z*se],'lags':lags,'n':n,'confidence':confidence,
            'status':'degenerate_identical_estimand' if se<=1e-12 else 'estimated',
            'caveat':'Fixed paired strategies, aligned daily excess returns, not adaptive-selection correction'}


def paired_block_sharpe(a,b,block_length=None,resamples=500,seed=20261002,lags=None,confidence=.95):
    """Synchronized overlapping block bootstrap-t for a fixed paired contrast."""
    a,_,_=_sample(a);b,_,_=_sample(b);base=paired_sharpe_inference(a,b,lags,confidence);n=len(a)
    if block_length is None:block_length=max(2,round(n**(1/3)))
    if type(block_length) is not int or not 1<=block_length<=n//4 or resamples<200:raise ValueError('Invalid bootstrap controls')
    if base['standard_error']<=1e-12:
        return {'metric':'paired_studentized_moving_block_sharpe','status':'degenerate_contrast',
                'interval':[base['daily_difference']]*2,'valid_draws':0,'seed':seed}
    rng=np.random.default_rng(seed);offsets=np.arange(block_length);statistics=[]
    for _ in range(resamples):
        starts=rng.integers(0,n-block_length+1,size=math.ceil(n/block_length));indices=(starts[:,None]+offsets).ravel()[:n]
        try:replicate=paired_sharpe_inference(a[indices],b[indices],base['lags'],confidence)
        except ValueError:continue
        if replicate['standard_error']>1e-12:
            statistics.append((replicate['daily_difference']-base['daily_difference'])/replicate['standard_error'])
    if len(statistics)<.95*resamples:raise ValueError('Too many degenerate studentized replicates')
    tail=(1-confidence)/2;lo,hi=np.quantile(statistics,[tail,1-tail])
    return {'metric':'paired_studentized_moving_block_sharpe','daily_difference':base['daily_difference'],
            'interval':[base['daily_difference']-float(hi)*base['standard_error'],base['daily_difference']-float(lo)*base['standard_error']],
            'block_length':block_length,'resamples':resamples,'valid_draws':len(statistics),'seed':seed,
            'confidence':confidence,'lags':base['lags'],'status':'estimated',
            'caveat':'Shared sampled rows preserve cross-strategy dependence; bootstrap coverage approximate and block/lag sensitive, not a p-value or selection-bias cure'}
