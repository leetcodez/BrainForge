import asyncio,json,math,sqlite3
import pytest
import config
import orchestrator
from forge2_factory import build_factory
from forge2_storage import atomic_json,campaign_lock

class RecordedNetwork:
    offline_fixture=True
    """Deterministic in-memory adapter. Every response is a synthetic fixture."""
    def __init__(self):self.calls=[];self.alphas={}
    async def start_keepalive(self):pass
    async def close(self):pass
    async def request(self,method,endpoint,json=None):
        self.calls.append((method,endpoint))
        if method=='POST' and endpoint=='/simulations':
            aid='fixture'+str(len(self.alphas));self.alphas[aid]=json
            return {'status_code':201,'location':config.WQ_BASE_URL+'/job/'+aid,'json':{}}
        if endpoint.startswith('/job/'):
            return {'status_code':200,'json':{'status':'COMPLETE','alpha':endpoint.split('/')[-1]}}
        if endpoint.endswith('/correlations/self'):
            return {'status_code':200,'json':{'records':[]}}
        if endpoint.startswith('/alphas/'):
            return {'status_code':200,'json':{'is':{'sharpe':2.0,'turnover':.2,'returns':.15,'skewness':0,'kurtosis':0,'trackRecordLength':1000,'margin':.01,'drawdown':.1,
                'checks':[{'name':'LOW_SHARPE','result':'PASS','value':2}, {'name':'LOW_2YEAR_SHARPE','result':'PASS','value':1.8}]}}}
        raise AssertionError((method,endpoint))

@pytest.fixture
def engine_setup(tmp_path,monkeypatch):
    import db_manager
    from db_manager import DatabaseManager
    monkeypatch.setattr(orchestrator,'DatabaseManager',lambda:DatabaseManager(str(tmp_path/'memory.db')))
    monkeypatch.setattr(orchestrator,'NetworkEngine',RecordedNetwork)
    settings={'DEFAULT_REGION':'USA','DEFAULT_DELAY':1,'PRIMARY_UNIVERSE':'U','UNIVERSES':['U'],
        'DATA_DICTIONARY':['f1','f2'],'FIELD_GROUPS':{'fundamental':['f1','f2']},
        'POPULATION_SIZE':4,'REFINEMENT_ENABLED':False,'STARTUP_REFINE_ENABLED':False,
        'NEGATION_ENABLED':False,'NEGATION_RESUME_ENABLED':False,'SEED_LLM_ENABLED':False,
        'SEED_QUANT_FRACTION':0,'SEED_COVERAGE_FIRST':False,'RETURN_DECORR_SELECTION_ENABLED':False,
        'ORIGINALITY_ENABLED':False,'FSA_ENABLED':False,'SIMULATION_POLL_INTERVAL_SECS':0,
        'CHECKPOINT_PATH':str(tmp_path/'checkpoint.json'),'DEFLATION_MAX_TRIALS':0}
    for key,value in settings.items():monkeypatch.setattr(config,key,value,raising=False)
    pool=tmp_path/'seed_pool.json';pool.write_text(json.dumps([
        {'id':'f1','templates':['rank(f1)','-rank(f1)']},
        {'id':'f2','templates':['rank(f2)','-rank(f2)']}]))
    monkeypatch.setattr(config,'SEED_POOL_PATH',str(pool))
    meta=tmp_path/'meta.json';meta.write_text(json.dumps({'axes':{'region':'USA','delay':1},'primary_universe':'U','observed_universes':['U'],
      'active_fields':['f1','f2'],'fields':{'f1':{'multiplier':1.8,'base':['f1']},'f2':{'multiplier':1.5,'base':['f2']}},
      'field_metadata':{f:{'type':'MATRIX','dataset':'d','subcategory':'s','category':'fundamental','multiplier':m,
                          'availability':[['USA',1,'U',.9,m,1,1]]} for f,m in [('f1',1.8),('f2',1.5)]}}))
    return tmp_path,meta

def test_real_engine_runs_and_resumes_using_only_recorded_adapter(engine_setup):
    directory,meta=engine_setup
    async def exercise():
        factory=build_factory(meta)
        try:
            await factory.run(generations=1)
            assert factory.population
            before={r['expression']:r['fitness'] for r in factory.population}
            assert all(math.isfinite(v) for v in before.values())
            assert factory.network.calls and all('/submit' not in endpoint for _,endpoint in factory.network.calls)
        finally:await factory.shutdown()
        resumed=build_factory(meta)
        try:
            await resumed.initialize();await resumed._bootstrap_population()
            assert {r['expression']:r['fitness'] for r in resumed.population}==before
            assert not resumed.network.calls
            assert resumed.generation==1
        finally:await resumed.shutdown()
    asyncio.run(exercise())
    with sqlite3.connect(directory/'memory.db') as conn:
        assert conn.execute('SELECT COUNT(*) FROM alpha_checks').fetchone()[0]>0

def test_unobserved_settings_and_unknown_fields_never_reach_network(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta)
        try:
            r=await factory._simulate_alpha('rank(f1)','UNKNOWN_UNIVERSE',0)
            assert not r.valid
            r=await factory._simulate_alpha('rank(unknown)','U',0)
            assert not r.valid and not factory.network.calls
        finally:await factory.shutdown()
    asyncio.run(exercise())

def test_nsga_third_objective_changes_dominance_without_compensating_gates(monkeypatch):
    monkeypatch.setattr(config,'THIRD_OBJECTIVE_ENABLED',True,raising=False)
    rows=[{'fitness':2.,'turnover':.2,'expected_value':1}, {'fitness':1.,'turnover':.2,'expected_value':2}]
    obj=orchestrator.AlphaFactory.__new__(orchestrator.AlphaFactory)
    ranked=obj._nsga_ii_sort(rows)
    assert [r['rank'] for r in ranked]==[0,0]
    monkeypatch.setattr(config,'THIRD_OBJECTIVE_ENABLED',False)
    ranked=obj._nsga_ii_sort(rows)
    assert sorted(r['rank'] for r in ranked)==[0,1]

def test_missing_checks_cannot_qualify_despite_good_headline_metrics():
    result=orchestrator.SimulationResult('rank(f)','U',0,sharpe=3,turnover=.2)
    obj=orchestrator.AlphaFactory.__new__(orchestrator.AlphaFactory)
    assert not obj._passes_checks_gate(result)

def test_single_writer_lock_rejects_a_second_runner(tmp_path):
    with campaign_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with campaign_lock(tmp_path):pass

def test_failed_atomic_replace_keeps_previous_state(tmp_path,monkeypatch):
    import forge2_storage
    p=tmp_path/'state.json';atomic_json(p,{'version':1})
    def fail(*a):raise OSError('injected crash before commit')
    monkeypatch.setattr(forge2_storage.os,'replace',fail)
    with pytest.raises(OSError):atomic_json(p,{'version':2})
    assert json.loads(p.read_text())=={'version':1}
    assert not list(tmp_path.glob('*.tmp'))

def test_checkpoint_write_failure_does_not_silently_continue(tmp_path,monkeypatch):
    def fail(*a):raise OSError('injected disk failure')
    monkeypatch.setattr(orchestrator,'atomic_json',fail)
    obj=orchestrator.AlphaFactory.__new__(orchestrator.AlphaFactory)
    obj.generation=0;obj.submission_count=0;obj.population=[]
    with pytest.raises(RuntimeError):obj._save_checkpoint()

@pytest.mark.parametrize('enriched',[False,True])
def test_pending_completed_child_is_recovered_without_resimulation(engine_setup,enriched):
    directory,meta=engine_setup
    async def exercise():
        factory=build_factory(meta)
        await factory.run(generations=1)
        factory.generation=1
        child={'expression':'rank(f1 + f2)','universe':'U','decay':0}
        factory._save_checkpoint(pending_offspring=[child])
        if enriched:await factory._evaluate_population([child],allow_grid=False)
        else:await factory._simulate_alpha(child['expression'],'U',0)
        await factory.shutdown()
        resumed=build_factory(meta)
        try:
            await resumed.initialize();await resumed._bootstrap_population()
            resumed._recover_pending_keys={f"{child['expression']}|U|0"}
            results=await resumed._evaluate_population([child],allow_grid=False)
            assert len(results)==1
            assert any(r['expression']==child['expression'] for r in resumed.population)
            assert not resumed.network.calls
            with sqlite3.connect(directory/'memory.db') as db:
                assert db.execute('SELECT fitness FROM alpha_population WHERE expression=?',(child['expression'],)).fetchone()[0] is not None
        finally:await resumed.shutdown()
    asyncio.run(exercise())


def test_boundary_resume_restores_decision_state_and_next_proposals(engine_setup,monkeypatch):
    import random
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta)
        await factory.run(generations=1)
        # Enable startup behavior: exact resume must not call either expansion.
        factory.refined={'already_refined'};factory.experience=[{'expression':'bad','reason':'fixture'}]
        factory.winner_exprs=['rank(f1)'];factory._avoid_motifs={'rank'}
        factory._save_checkpoint()
        before=json.loads(json.dumps(factory.population))
        state=(list(factory.history_scores),factory.experience[:],factory.refined.copy(),factory._avoid_motifs.copy())
        def propose(obj):
            out=[]
            for _ in range(8):
                p1,p2=obj._select_parents()
                expr=obj.genetic.mutate(obj.genetic.crossover(p1['expression'],p2['expression']))
                out.append((expr,obj._seed_decay(expr)))
            return out,random.getstate()
        expected=propose(factory)
        await factory.shutdown()
        resumed=build_factory(meta)
        async def forbidden():raise AssertionError('startup expansion on exact continuation')
        resumed._harvest_resumed_negatives=forbidden;resumed._refine_resumed_winners=forbidden
        try:
            await resumed.initialize();await resumed._bootstrap_population()
            assert resumed.population==before
            assert (resumed.history_scores,resumed.experience,resumed.refined,resumed._avoid_motifs)==state
            assert propose(resumed)==expected
        finally:await resumed.shutdown()
    asyncio.run(exercise())


def test_empty_checkpoint_population_does_not_seed_again(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        factory.population=[];factory._save_checkpoint();await factory.shutdown()
        resumed=build_factory(meta)
        try:
            await resumed.initialize();await resumed._bootstrap_population()
            assert resumed.population==[] and not resumed.network.calls
        finally:await resumed.shutdown()
    asyncio.run(exercise())


def test_position_count_is_not_dsr_track_record_length(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        request=factory.network.request
        async def with_counts(method,endpoint,json=None):
            response=await request(method,endpoint,json=json)
            if endpoint.startswith('/alphas/') and not endpoint.endswith('/correlations/self'):
                response['json']['is']['longCount']=50000
            return response
        factory.network.request=with_counts
        try:
            result=await factory._simulate_alpha('rank(f1)','U',0)
            assert result.track_record_length==1000
        finally:await factory.shutdown()
    asyncio.run(exercise())


@pytest.mark.parametrize('malformed',[{'status_code':500,'json':{}},{'status_code':200,'json':{}},{'status_code':200,'json':{'records':[{'correlation':'unknown'}]}},{'status_code':200,'json':{'records':[{'correlation':1.1}]}}])
def test_correlation_missing_or_bad_response_cannot_be_perfectly_decorrelated(engine_setup,monkeypatch,malformed):
    _,meta=engine_setup;monkeypatch.setattr(config,'CORRELATION_CHECK_ATTEMPTS',1)
    async def exercise():
        factory=build_factory(meta)
        async def response(*a,**k):return malformed
        factory.network.request=response
        try:assert await factory._check_correlation('a') is None
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_unknown_risk_evidence_fails_configured_gates(monkeypatch):
    monkeypatch.setattr(config,'DRAWDOWN_MARGIN_GATE_ENABLED',True)
    monkeypatch.setattr(config,'MAX_DRAWDOWN',.2);monkeypatch.setattr(config,'MIN_MARGIN',0.)
    obj=orchestrator.AlphaFactory.__new__(orchestrator.AlphaFactory)
    result=orchestrator.SimulationResult('rank(f)','U',0)
    assert not obj._passes_risk_gates(result) and obj._risk_fail_reason(result)=='unknown_drawdown'
    result.drawdown=.1
    assert not obj._passes_risk_gates(result) and obj._risk_fail_reason(result)=='unknown_margin'


def test_preflight_budget_rejects_expensive_expression_before_dispatch(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta)
        try:
            result=await factory._simulate_alpha('ts_mean(f1,2000)','U',0)
            assert not result.valid and not factory.network.calls
            assert factory.experiment_ledger.summary()['events']==0
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_accepted_receipt_is_polled_without_another_simulation_post(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        payload=config.build_simulation_payload('rank(f1)','U',0)
        attempt=factory.experiment_ledger.prepare(payload,factory.experiment_context)
        factory.experiment_ledger.dispatch(attempt['attempt_id'])
        factory.experiment_ledger.accept(attempt['attempt_id'],config.WQ_BASE_URL+'/job/prepaid',__import__('time').time()+60)
        try:
            result=await factory._simulate_alpha('rank(f1)','U',0)
            assert result.valid and result.alpha_id=='prepaid'
            assert all(method!='POST' for method,_ in factory.network.calls)
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_indeterminate_dispatch_stops_without_reposting(engine_setup):
    from forge2_experiments import IndeterminateAttemptError
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        payload=config.build_simulation_payload('rank(f1)','U',0)
        attempt=factory.experiment_ledger.prepare(payload,factory.experiment_context)
        factory.experiment_ledger.dispatch(attempt['attempt_id'])
        try:
            with pytest.raises(IndeterminateAttemptError):await factory._simulate_alpha('rank(f1)','U',0)
            assert not factory.network.calls
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_remote_complete_but_detail_failure_recovers_by_get_only(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        request=factory.network.request
        async def fail_detail(method,endpoint,json=None):
            if endpoint.startswith('/alphas/'):return {'status_code':500,'json':{}}
            return await request(method,endpoint,json=json)
        factory.network.request=fail_detail
        with pytest.raises(RuntimeError,match='detail'):await factory._simulate_alpha('rank(f1)','U',0)
        assert factory.experiment_ledger.summary()['states']=={'remote_complete':1}
        await factory.shutdown()
        resumed=build_factory(meta);await resumed.initialize()
        try:
            assert (await resumed._simulate_alpha('rank(f1)','U',0)).valid
            assert all(method=='GET' for method,_ in resumed.network.calls)
        finally:await resumed.shutdown()
    asyncio.run(exercise())


def test_completed_receipt_survives_derived_db_save_failure_without_any_network(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        async def disk_failure(*a,**k):raise OSError('derived DB fixture failure')
        factory.db.save_alpha=disk_failure
        with pytest.raises(OSError):await factory._simulate_alpha('rank(f1)','U',0)
        assert factory.experiment_ledger.summary()['states']=={'completed':1}
        await factory.shutdown()
        resumed=build_factory(meta);await resumed.initialize()
        try:
            result=await resumed._simulate_alpha('rank(f1)','U',0)
            assert result.valid and not resumed.network.calls
        finally:await resumed.shutdown()
    asyncio.run(exercise())


def test_poll_receipt_does_not_forward_credentials_outside_configured_api(engine_setup):
    from forge2_experiments import IndeterminateAttemptError
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        p=config.build_simulation_payload('rank(f1)','U',0);a=factory.experiment_ledger.prepare(p,factory.experiment_context)
        factory.experiment_ledger.dispatch(a['attempt_id']);factory.experiment_ledger.accept(a['attempt_id'],'https://untrusted.example/job')
        try:
            with pytest.raises(IndeterminateAttemptError):await factory._simulate_alpha('rank(f1)','U',0)
            assert not factory.network.calls
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_actual_engine_basket_selection_uses_saved_pnl_only(engine_setup,monkeypatch):
    import datetime
    import numpy as np
    _,meta=engine_setup
    monkeypatch.setattr(config,'BASKET_DATASET_FRACTION',1.,raising=False)
    async def exercise():
        factory=build_factory(meta);await factory.initialize()
        monkeypatch.setattr(config,'BASKET_DATASET_FRACTION',1.)
        rng=np.random.default_rng(90);x=rng.normal(size=200);y=rng.normal(size=200)
        dates=[(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat() for i in range(200)]
        factory.population=[]
        for aid,expr,value in [('a','rank(f1)',x),('dup','ts_mean(f1,20)',x),('b','rank(f2)',y)]:
            factory.population.append({'alpha_id':aid,'expression':expr,'universe':'U','decay':0,'sharpe':2,'fitness':2,'turnover':.2,'returns':.15})
            await factory.db.save_pnl(aid,list(zip(dates,np.cumsum(value).tolist())))
        try:
            selected=await factory._select_generation_survivors()
            assert 'dup' not in [r['alpha_id'] for r in selected]
            assert factory.basket_report['verified'] and not factory.network.calls
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_real_transport_is_refused_before_keepalive_in_offline_mode(engine_setup):
    _,meta=engine_setup
    async def exercise():
        factory=build_factory(meta);factory.network.offline_fixture=False
        try:
            with pytest.raises(RuntimeError,match='offline research mode'):await factory.initialize()
            assert not factory.network.calls
        finally:await factory.shutdown()
    asyncio.run(exercise())


def test_duplicate_pending_candidates_merge_once_and_repeat_recovery_is_noop(engine_setup):
    _,meta=engine_setup
    async def exercise():
        f=build_factory(meta);await f.run(generations=1);f.generation=1
        child={'expression':'rank(f1 + f2)','universe':'U','decay':0}
        f._save_checkpoint(pending_offspring=[child,child]);await f._evaluate_population([child],allow_grid=False);await f.shutdown()
        g=build_factory(meta);await g.initialize();await g._bootstrap_population();g._recover_pending_keys={'rank(f1 + f2)|U|0'}
        try:
            before=len(g.history_scores);out=await g._evaluate_population([child,child],allow_grid=False)
            assert len(out)==1 and len(g.history_scores)==before+1
            assert len([r for r in g.population if r['expression']==child['expression']])==1
            population=[dict(r) for r in g.population];history=list(g.history_scores)
            assert await g._evaluate_population([child],allow_grid=False)==[]
            assert g.population==population and g.history_scores==history and not g.network.calls
        finally:await g.shutdown()
    asyncio.run(exercise())


def test_accepted_receipt_recovery_repairs_missed_shared_trial_counter(engine_setup,monkeypatch):
    import time
    directory,meta=engine_setup
    monkeypatch.setenv('FORGE2_TRIAL_LEDGER',str(directory/'shared_trials.sqlite'))
    async def exercise():
        f=build_factory(meta);await f.initialize();payload=config.build_simulation_payload('rank(f1)','U',0)
        a=f.experiment_ledger.prepare(payload,f.experiment_context)
        f.experiment_ledger.dispatch(a['attempt_id']);f.experiment_ledger.accept(a['attempt_id'],config.WQ_BASE_URL+'/job/prepaid',time.time()+60)
        assert f.trial_ledger.count()==0
        try:
            assert (await f._simulate_alpha('rank(f1)','U',0)).valid
            assert f.trial_ledger.count()==1
            assert all(method=='GET' for method,_ in f.network.calls)
            await f._simulate_alpha('rank(f1)','U',0)
            assert f.trial_ledger.count()==1
        finally:await f.shutdown()
    asyncio.run(exercise())
