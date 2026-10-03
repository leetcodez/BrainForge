import datetime
import numpy as np
import pytest
from forge2_search import expression_identity,candidate_identity,budget_errors
from forge2_portfolio import select_basket,dataset_members


def fixture_data():
    rng=np.random.default_rng(6);x=rng.normal(size=500);y=rng.normal(size=500);z=rng.normal(size=500)
    times=[(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(500)]
    series={k:dict(zip(times,np.cumsum(v))) for k,v in [('a',x),('duplicate',x),('flip',-x),('b',y),('blend',x+y),('c',z)]}
    rows=[{'alpha_id':k,'expression':'rank('+k+')','universe':'U'} for k in series]
    meta={k:{'dataset':'d'+k,'type':'MATRIX'} for k in series}
    return rows,series,meta


def test_basket_does_not_reward_duplicates_or_sign_flips():
    rows,series,meta=fixture_data()
    selected,report=select_basket(rows,series,meta,4,explore_fraction=0,max_abs_correlation=.7)
    ids=[r['alpha_id'] for r in selected]
    assert ids==['a','b','c']
    assert report['rejections']['duplicate']==report['rejections']['flip']=='absolute_return_redundancy'
    assert report['shrinkage'] is not None and report['common_intervals']>=60


def test_linear_combination_is_rejected_by_conditional_not_just_pairwise_redundancy():
    rows,series,meta=fixture_data();rows=[r for r in rows if r['alpha_id'] in {'a','b','blend','c'}]
    selected,report=select_basket(rows,series,meta,4,explore_fraction=0,max_abs_correlation=.9,min_residual_fraction=.15)
    assert 'blend' not in [r['alpha_id'] for r in selected]
    assert report['rejections']['blend'] in {'low_conditional_residual_novelty','raw_linear_subspace_redundancy'}


def test_dataset_caps_apply_to_all_mixed_signal_datasets():
    meta={'x':{'dataset':'d1','type':'MATRIX'},'y':{'dataset':'d2','type':'MATRIX'},'group':{'dataset':'d3','type':'GROUP'}}
    assert dataset_members('group_neutralize(rank(x+y),group)',meta)==['d1','d2']
    rows,series,meta=fixture_data()
    for rec in meta.values():rec['dataset']='same'
    selected,report=select_basket(rows,series,meta,5,max_dataset_fraction=.2,explore_fraction=0)
    assert len(selected)==1 and report['dataset_counts']=={'same':1}


def test_unknown_overlap_remains_unverified_and_regimes_cannot_mix():
    rows,series,meta=fixture_data();chosen,report=select_basket(rows,{},meta,3)
    assert len(chosen)==3 and not report['verified'] and 'unverified' in report['reason']
    rows[1]['universe']='different'
    with pytest.raises(ValueError):select_basket(rows,series,meta,3)


def test_safe_identity_normalizes_whitespace_not_financial_algebra():
    assert expression_identity('rank(f + g)')==expression_identity('rank( (f+g))')
    assert expression_identity('rank(-f)')!=expression_identity('-rank(f)')
    assert expression_identity('f/g')!=expression_identity('f/max(abs(g),0.001)')
    assert candidate_identity({'regular':'rank(f)','settings':{'delay':1}},'data1')!=candidate_identity({'regular':'rank(f)','settings':{'delay':0}},'data1')


def test_expression_resource_budgets_and_window_roles():
    assert 'lookback_budget' in budget_errors('ts_mean(f,2000)')
    assert 'lookback_budget' in budget_errors('ts_backfill(f,lookback=2000)')
    assert not budget_errors('rank(f,rate=2000)')
    assert 'operator_call_budget' in budget_errors('rank(rank(f))',max_calls=1)
    assert 'field_count_budget' in budget_errors('f+g',max_fields=1)


def test_executable_canonicalization_preserves_tree_control_order_and_literal_precision():
    from syntax_validator import SyntaxValidator
    import ast
    a='(1e16 + -1e16) + 1';b='1e16 + (-1e16 + 1)'
    ca=SyntaxValidator.canonicalize(a);cb=SyntaxValidator.canonicalize(b)
    assert eval(ca)==1 and eval(cb)==0 and ca!=cb
    assert SyntaxValidator.canonicalize('multiply(z, a, 0)')=='multiply(z, a, 0)'
    c=SyntaxValidator.canonicalize('rank(f + 1.0000000000000001)')
    assert '1.0000000000000001' in c
    assert expression_identity(c)!=expression_identity('rank(f + 1.0)')
    assert SyntaxValidator.canonicalize('max(-0.0, 0.0)')=='max(-0.0, 0.0)'


def test_old_winner_rank_is_not_labeled_cscv_pbo():
    from oos_deflation import OOSDeflationEngine
    assert OOSDeflationEngine.single_split_winner_rank([]) is None
    assert OOSDeflationEngine.single_split_winner_rank([(4,1),(3,4),(2,3),(1,2)])==.75


def test_ridge_residual_formula_matches_direct_centered_residual_variance():
    from forge2_portfolio import residual_fraction
    rng=np.random.default_rng(7);x=rng.normal(size=(500,3));x[:,2]=x[:,0]+x[:,1]+rng.normal(0,.2,500)
    x=(x-x.mean(axis=0))/x.std(axis=0);raw=np.corrcoef(x,rowvar=False)
    shrunk=.8*raw+.2*np.eye(3);ids=[0,1];ridge=.2
    b=np.linalg.solve(shrunk[np.ix_(ids,ids)]+ridge*np.eye(2),shrunk[2,ids])
    assert np.isclose(residual_fraction(raw,shrunk,2,ids,ridge),np.var(x[:,2]-x[:,ids]@b))


def test_primary_universe_prefers_recorded_configured_preference_or_explicit_override(monkeypatch):
    from forge2_vocabulary import VocabularyBuilder
    import forge2_config as F2
    cat=type('Catalog',(),{'observed_universes':lambda self,r,d:['ILLIQUID_MINVOL1M','TOP3000']})()
    monkeypatch.setitem(F2.PRIMARY_UNIVERSE_BY_REGION,'USA','TOP3000')
    monkeypatch.delenv('FORGE2_PRIMARY_UNIVERSE',raising=False)
    assert VocabularyBuilder(cat,'USA',1,{'rank'}).primary_universe=='TOP3000'
    monkeypatch.setenv('FORGE2_PRIMARY_UNIVERSE','ILLIQUID_MINVOL1M')
    b=VocabularyBuilder(cat,'USA',1,{'rank'})
    assert b.primary_universe=='ILLIQUID_MINVOL1M' and b.universe_selection_reason=='explicit_recorded_override'
    monkeypatch.setenv('FORGE2_PRIMARY_UNIVERSE','unrecorded')
    with pytest.raises(ValueError):VocabularyBuilder(cat,'USA',1,{'rank'})


def test_exact_blend_is_not_novel_under_high_dimensional_strong_shrinkage():
    rng=np.random.default_rng(6);x,y,z=rng.normal(size=(3,100))
    vectors={'a':x,'b':y,'blend':x+y,**{'noise'+str(i):rng.normal(size=100) for i in range(100)}}
    dates=[(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(100)]
    series={aid:dict(zip(dates,np.cumsum(v))) for aid,v in vectors.items()}
    rows=[{'alpha_id':aid,'expression':'rank('+aid+')','universe':'U'} for aid in vectors]
    meta={aid:{'dataset':aid,'type':'MATRIX'} for aid in vectors}
    chosen,report=select_basket(rows,series,meta,3,explore_fraction=0,max_dataset_fraction=1)
    assert report['shrinkage']>.9 and 'blend' not in [r['alpha_id'] for r in chosen]
    assert report['rejections']['blend']=='raw_linear_subspace_redundancy'


def test_exploration_reserve_cannot_admit_known_sign_flip_pair():
    rows,series,meta=fixture_data()
    chosen,report=select_basket(rows,series,meta,4,explore_fraction=.75,max_dataset_fraction=1)
    assert not {'a','flip'}<=set(r['alpha_id'] for r in chosen)
    assert not {'a','duplicate'}<=set(r['alpha_id'] for r in chosen)


def test_near_blend_is_not_made_novel_by_strong_shrinkage():
    rng=np.random.default_rng(67);x,y,z=rng.normal(size=(3,100))
    values={'a':x,'b':y,'near_blend':x+y+.001*z,**{'noise'+str(i):rng.normal(size=100) for i in range(100)}}
    dates=[(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(100)]
    series={k:dict(zip(dates,np.cumsum(v))) for k,v in values.items()}
    rows=[{'alpha_id':k,'expression':'rank('+k+')','universe':'U'} for k in values]
    meta={k:{'type':'MATRIX','dataset':k} for k in values}
    chosen,report=select_basket(rows,series,meta,3,explore_fraction=0,max_dataset_fraction=1)
    assert 'near_blend' not in [r['alpha_id'] for r in chosen]
