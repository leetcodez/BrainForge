import json,sqlite3
import pytest
import config
from forge2_policy import fingerprint,guard
from forge2_trials import TrialLedger


def test_effective_gate_and_operator_definition_change_policy(tmp_path,monkeypatch):
    op=tmp_path/'ops.json';op.write_text(json.dumps([{'name':'rank','definition':'rank(x)'}]))
    original=fingerprint(config,'catalog',op)
    guard(tmp_path/'policy.json',original,False)
    monkeypatch.setattr(config,'MAX_DRAWDOWN',.0123)
    changed=fingerprint(config,'catalog',op)
    assert changed['fingerprint']!=original['fingerprint']
    with pytest.raises(ValueError):guard(tmp_path/'policy.json',changed,True)
    op.write_text(json.dumps([{'name':'rank','definition':'rank(x,rate=2)'}]))
    assert fingerprint(config,'catalog',op)['fingerprint']!=changed['fingerprint']


def test_full_trial_payload_is_persisted(tmp_path):
    ledger=TrialLedger(tmp_path/'ledger.db')
    payload={'regular':'rank(f)','settings':{'neutralization':'INDUSTRY','region':'USA','delay':1,'universe':'U','decay':0}}
    ledger.record('USA_d1','rank(f)','U',0,payload)
    with sqlite3.connect(ledger.path) as db:
        assert json.loads(db.execute('SELECT payload_json FROM trial_payloads').fetchone()[0])==payload


def test_pending_campaign_reuses_epoch_without_sampling(tmp_path,monkeypatch):
    from test_campaign import setup_campaign
    import forge2_campaign as campaign
    cdir=setup_campaign(tmp_path,monkeypatch)
    (cdir/'checkpoint.json').write_text(json.dumps({'pending_offspring':[{'expression':'rank(f)'}]}))
    (cdir/'forge2_epoch_manifest.json').write_text(json.dumps({'epoch_id':'pinned'}))
    def forbidden(*a):raise AssertionError('vocabulary/exposure/RNG rotation on pending restart')
    monkeypatch.setattr(campaign,'build_vocabulary',forbidden)
    monkeypatch.setattr(campaign,'run_burst_subprocess',lambda *a:1)
    with pytest.raises(RuntimeError,match='Burst failed'):campaign.main()


def test_epoch_commit_failure_preserves_previous_controls(tmp_path,monkeypatch):
    import forge2_vocabulary as vocabulary
    from forge2_storage import atomic_json
    from forge2_bandit import DatasetBandit
    import forge2_config as F2
    builder=vocabulary.VocabularyBuilder.__new__(vocabulary.VocabularyBuilder)
    builder.catalog=type('Catalog',(),{'catalog_hash':'h'})()
    builder.bandit=DatasetBandit(tmp_path/F2.BANDIT_STATE_FILE)
    builder.exposures={}
    builder.build=lambda:{'rows':[],'seed_pool':[],'stats':{},'meta':{'fields':{'f':{'class':'base'}},'field_metadata':{'f':{'type':'MATRIX'}}}}
    builder.write(tmp_path)
    committed=(tmp_path/'forge2_epoch_manifest.json').read_bytes()
    manifest=json.loads(committed);edir=tmp_path/manifest['epoch_dir']
    controls=[(edir/name).read_bytes() for name in ['forge2_exploration.json',F2.BANDIT_STATE_FILE]]
    def fail_manifest(path,value):
        if path.name=='forge2_epoch_manifest.json':raise OSError('crash before epoch commit')
        atomic_json(path,value)
    monkeypatch.setattr(vocabulary,'atomic_json',fail_manifest)
    with pytest.raises(OSError):builder.write(tmp_path)
    assert (tmp_path/'forge2_epoch_manifest.json').read_bytes()==committed
    assert [(edir/name).read_bytes() for name in ['forge2_exploration.json',F2.BANDIT_STATE_FILE]]==controls


def test_distinct_full_settings_count_as_distinct_observed_trials(tmp_path):
    ledger=TrialLedger(tmp_path/'ledger.db')
    for neutralization in ['INDUSTRY','SECTOR','SECTOR']:
        ledger.record('USA_d1','rank(f)','U',0,{'regular':'rank(f)','settings':{'universe':'U','decay':0,'neutralization':neutralization}})
    assert ledger.count()==2


def test_policy_does_not_change_when_only_epoch_or_operational_paths_move(tmp_path,monkeypatch):
    op=tmp_path/'ops.json';op.write_text(json.dumps([{'name':'rank','definition':'rank(x)'}]))
    before=fingerprint(config,'catalog',op)['fingerprint']
    for attr in ['FIELD_CATALOG_PATH','CHECKPOINT_PATH','SEED_POOL_PATH','SESSION_CACHE_PATH','REAUTH_FLAG_PATH']:
        monkeypatch.setattr(config,attr,str(tmp_path/attr))
    assert fingerprint(config,'catalog',op)['fingerprint']==before
