import datetime,json
import numpy as np
import pytest
from forge2_inference import sharpe_inference,moving_block_sharpe
from forge2_protocol import forward_folds,register_protocol,HoldoutSeal


def test_hac_zero_lags_matches_influence_iid_and_positive_autocorrelation_increases_uncertainty():
    rng=np.random.default_rng(9);noise=rng.normal(0,.01,4000);x=noise.copy()
    for i in range(1,len(x)):x[i]+=.75*x[i-1]
    iid=sharpe_inference(x,lags=0);hac=sharpe_inference(x,lags=12)
    assert iid['daily_standard_error']==iid['iid_standard_error']
    assert hac['daily_standard_error']>1.7*iid['daily_standard_error']
    assert hac['daily_interval'][0]<hac['daily_sharpe']<hac['daily_interval'][1]


def test_block_bootstrap_is_reproducible_and_scale_invariant():
    x=np.random.default_rng(4).normal(.0002,.01,400)
    a=moving_block_sharpe(x,8,300,42);b=moving_block_sharpe(x*10,8,300,42)
    assert a==moving_block_sharpe(x,8,300,42)
    assert np.allclose(a['daily_percentile_interval'],b['daily_percentile_interval'])


@pytest.mark.parametrize('x',[np.zeros(50),[1,2],np.r_[np.ones(50),np.nan]])
def test_invalid_return_samples_do_not_get_false_confidence(x):
    with pytest.raises(ValueError):sharpe_inference(x)


def dates(n=750):return [(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(n)]


def test_forward_folds_never_train_on_future_or_touch_final_holdout():
    plan=forward_folds(dates(),100,40,20,100,label_horizon=10,max_lookback=20)
    for fold in plan['folds']:
        assert fold['train'][1]+20==fold['test'][0]
        assert fold['test'][1]<=plan['development'][1]<plan['holdout'][0]
    with pytest.raises(ValueError):forward_folds(dates(),gap=2,label_horizon=20,max_lookback=20)
    with pytest.raises(ValueError):forward_folds(dates()[::-1])


def test_registration_and_holdout_are_immutable_and_candidate_bound(tmp_path):
    p=forward_folds(dates(),100,40,20,100)
    record=register_protocol(tmp_path/'protocol.json',p,'data','policy',previously_viewed=False,data_exposure_namespace='DATA')
    with pytest.raises(ValueError):register_protocol(tmp_path/'protocol.json',p,'new','policy')
    seal=HoldoutSeal(tmp_path/'seal.sqlite')
    with pytest.raises(ValueError):seal.evaluate(record,'candidate','different',lambda _:None)
    assert seal.evaluate(record,'candidate','data',lambda interval:{'interval':interval})['interval']==p['holdout']
    with pytest.raises(ValueError):seal.evaluate(record,'other_candidate','data',lambda _:None)


def test_crashed_holdout_stays_claimed_and_viewed_data_cannot_be_untouched(tmp_path):
    record=register_protocol(tmp_path/'protocol.json',forward_folds(dates()),'data','policy',previously_viewed=False,data_exposure_namespace='DATA')
    def crash(_):raise RuntimeError('fixture crash')
    seal=HoldoutSeal(tmp_path/'seal.sqlite')
    with pytest.raises(RuntimeError):seal.evaluate(record,'frozen','data',crash)
    with pytest.raises(ValueError):seal.evaluate(record,'frozen','data',lambda _:None)
    record['previously_viewed']=True
    with pytest.raises(ValueError):HoldoutSeal(tmp_path/'different.sqlite').evaluate(record,'frozen','data',lambda _:None)


def test_event_aware_purge_detects_variable_horizons_and_asof_leakage():
    from forge2_protocol import purge_forward_events
    def event(day,end=None,availability=None,feature=None):
        end=end or day
        return {'decision_time':f'2020-01-{day:02}','outcome_start':f'2020-01-{day:02}',
                'outcome_end':f'2020-01-{end:02}','label_available_at':f'2020-01-{(availability or end):02}',
                'feature_available_at':f'2020-01-{(feature or day):02}'}
    rows=[event(1),event(2,10),event(3,3,12),event(4,4,4,5),event(10),event(11)]
    result=purge_forward_events(rows,[4])
    assert result['train_indices']==[0]
    assert result['excluded']['1']=='overlapping_outcome_information'
    assert result['excluded']['2']=='label_not_available_at_train_cutoff'
    assert result['excluded']['3']=='feature_not_available_as_of_decision'
    assert result['excluded']['5']=='not_strictly_forward'


def test_paired_hac_and_synchronized_studentized_blocks_preserve_clones():
    from forge2_inference import paired_sharpe_inference,paired_block_sharpe
    x=np.random.default_rng(91).normal(.001,.01,500)
    identical=paired_sharpe_inference(x,x)
    assert identical['standard_error']==0 and identical['interval']==[0.,0.]
    assert paired_block_sharpe(x,x)['status']=='degenerate_contrast'
    y=x+np.random.default_rng(11).normal(0,.005,500)
    a=paired_block_sharpe(x,y,8,200,42)
    assert a==paired_block_sharpe(x,y,8,200,42) and a['valid_draws']==200
    assert a['interval'][0]<=a['interval'][1]


def test_cscv_matches_small_manual_rank_enumeration_and_budget():
    from forge2_cscv import cscv_fixed_pool
    from itertools import combinations
    from scipy.stats import rankdata
    rng=np.random.default_rng(8);x=rng.normal(size=(80,3));x[:40,0]+=1.;x[40:,0]-=1.
    out=cscv_fixed_pool(x,4)
    expected=[];indices=np.arange(80).reshape(4,20)
    for chosen in combinations(range(4),2):
        test=[i for i in range(4) if i not in chosen]
        a=x[indices[list(chosen)].ravel()];b=x[indices[test].ravel()]
        w=np.argmax(a.mean(0)/a.std(0));rank=rankdata(b.mean(0)/b.std(0))[w]/4
        expected.append(rank<.5)
    assert out['partitions']==6 and out['fraction_negative_logits']==sum(expected)/6
    with pytest.raises(ValueError):cscv_fixed_pool(x,4,max_partitions=5)
    with pytest.raises(ValueError):cscv_fixed_pool(x[:-1],4)


def test_re_registration_cannot_reset_exposed_holdout_observations(tmp_path):
    plan=forward_folds(dates());seal=HoldoutSeal(tmp_path/'seal.sqlite')
    a=register_protocol(tmp_path/'a.json',plan,'DATA','POLICY',previously_viewed=False,data_exposure_namespace='DATA')
    seal.evaluate(a,'CANDIDATE','DATA',lambda _:{'recorded':True})
    b=register_protocol(tmp_path/'b.json',plan,'DATA','CHANGED_POLICY',previously_viewed=False,data_exposure_namespace='DATA')
    with pytest.raises(ValueError,match='observations already'):seal.evaluate(b,'DIFFERENT_CANDIDATE','DATA',lambda _:True)
    overlapping=forward_folds(dates(),holdout_size=100)
    c=register_protocol(tmp_path/'c.json',overlapping,'REENCODED_DATA','POLICY',previously_viewed=False,data_exposure_namespace='DATA')
    with pytest.raises(ValueError):seal.evaluate(c,'CANDIDATE','REENCODED_DATA',lambda _:True)


def test_validation_features_must_be_available_at_decision_but_future_outcomes_are_allowed():
    from forge2_protocol import purge_forward_events
    rows=[{'decision_time':'2020-01-01','outcome_start':'2020-01-01','outcome_end':'2020-01-01','label_available_at':'2020-01-01','feature_available_at':'2020-01-01'},
          {'decision_time':'2020-01-02','outcome_start':'2020-01-02','outcome_end':'2020-01-03','label_available_at':'2020-01-03','feature_available_at':'2020-01-03'}]
    with pytest.raises(ValueError,match='Validation'):purge_forward_events(rows,[1])
    rows[1]['feature_available_at']='2020-01-02'
    assert purge_forward_events(rows,[1])['train_indices']==[0]


def test_hac_matches_independent_delta_gradient_bartlett_calculation():
    x=np.random.default_rng(456).normal(.002,.01,100);n=len(x);mu=x.mean();m2=np.mean(x*x);variance=m2-mu*mu
    gradient=np.array([m2/variance**1.5,-mu/(2*variance**1.5)])
    moments=np.column_stack([x-mu,x*x-m2]);psi=moments@gradient
    omega=float(sum(v*v for v in psi)/n)
    for lag in range(1,5):
        covariance=sum(psi[t]*psi[t-lag] for t in range(lag,n))/n
        omega+=2*(1-lag/5)*covariance
    expected=(omega/n)**.5
    assert np.isclose(sharpe_inference(x,lags=4)['daily_standard_error'],expected,rtol=1e-12)


def test_untouched_claim_requires_stable_namespace_not_artifact_encoding(tmp_path):
    with pytest.raises(ValueError,match='stable exposure namespace'):
        register_protocol(tmp_path/'r.json',forward_folds(dates()),'file_bytes_hash','policy',previously_viewed=False)
