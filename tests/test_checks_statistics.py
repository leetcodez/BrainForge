import datetime,random
from forge2_checks import parse_checks
from forge2_statistics import diversification_diagnostics,daily_changes
from forge2_trials import TrialLedger

def test_missing_and_unknown_checks_are_unverified():
    for m in [{},{'checks':[]},{'checks':[{'name':'X','result':'NEW_STATE'}]}]:assert not parse_checks(m).verified

def test_checks_preserve_raw_warnings_pending_and_consultant_values():
    raw=[{'name':'LOW_2YEAR_SHARPE','result':'PASS','value':1.7,'limit':1.58},
         {'name':'LOW_PNL_REALIZATION','result':'FAIL','value':13},
         {'name':'SELF_CORRELATION','result':'PENDING'},
         {'name':'NEW_CHECK','result':'WARNING'}]
    p=parse_checks({'checks':raw,'pyramidMultiplier':1.8})
    assert p.verified and p.raw==raw and p.sharpe_2y==1.7 and p.pnl_realization==13
    assert p.failed==['LOW_PNL_REALIZATION'] and p.warnings==['NEW_CHECK'] and p.pending==['SELF_CORRELATION']
    assert p.pyramid_multiplier==1.8

def series(seed,shift=0):
    rng=random.Random(seed);level=0;out={}
    for i in range(200):
        date=datetime.date(2020,1,1)+datetime.timedelta(days=i+shift)
        level+=rng.gauss(0,1);out[date.isoformat()]=level
    return out

def test_missing_overlap_never_implies_independence():
    d=diversification_diagnostics({'a':series(1),'b':series(2,500)})
    assert d['value'] is None and d['reason']=='insufficient_common_overlap'

def test_identical_series_have_effective_rank_one():
    d=diversification_diagnostics({'a':series(1),'b':series(1),'c':series(1)})
    assert abs(d['value']-1)<1e-8
    assert d['metric']=='spectral_effective_rank'

def test_long_pnl_gaps_are_not_mislabeled_as_daily_changes():
    assert daily_changes({'2020-01-01':0,'2020-02-01':50,'2020-02-02':52})=={('2020-02-01','2020-02-02'):2}

def test_trial_ledger_counts_unique_hypotheses_across_campaigns(tmp_path):
    p=tmp_path/'trials.sqlite';l=TrialLedger(p)
    l.record('USA_d1','rank(f)','U',0);l.record('USA_d1','rank(f)','U',0)
    l.record('USA_d0','rank(f)','U',0)
    assert TrialLedger(p).count()==2


def test_different_start_dates_never_share_an_increment_observation():
    from oos_deflation import OOSDeflationEngine
    a={'2020-01-01':0,'2020-01-03':5,'2020-01-04':7}
    b={'2020-01-01':0,'2020-01-02':2,'2020-01-03':5,'2020-01-04':7}
    x,y=OOSDeflationEngine._aligned_pnl_increments(a,b,min_overlap=2)
    assert x is None and y is None
