import sqlite3
import pytest
from forge2_bandit import DatasetBandit

def make_db(p):
    con=sqlite3.connect(p)
    con.execute('CREATE TABLE alpha_population(id INTEGER PRIMARY KEY,expression TEXT,sharpe REAL,turnover REAL,is_qualified INTEGER,failed_checks TEXT,fitness REAL)')
    con.execute("INSERT INTO alpha_population VALUES(1,'rank(f)',2,.2,0,'CONCENTRATION',1)")
    con.commit();con.close()

def test_learning_replay_is_idempotent_and_failed_checks_are_not_successes(tmp_path):
    db=tmp_path/'memory.db';make_db(db)
    bandit=DatasetBandit(tmp_path/'bandit.json')
    bandit.update_from_db(db,{'f':'dataset'})
    first=bandit.summary()
    bandit.save()
    reloaded=DatasetBandit(tmp_path/'bandit.json')
    reloaded.update_from_db(db,{'f':'dataset'})
    assert reloaded.summary()==first
    arm=reloaded.arms['dataset']
    assert arm['a']==arm['prior_a']
    assert arm['b']==arm['prior_b']+1

def test_enrichment_below_the_old_watermark_is_not_lost(tmp_path):
    db=tmp_path/'memory.db';make_db(db)
    b=DatasetBandit(tmp_path/'bandit.json');b.update_from_db(db,{'f':'dataset'})
    with sqlite3.connect(db) as c:c.execute("UPDATE alpha_population SET is_qualified=1,failed_checks='' WHERE id=1")
    b.update_from_db(db,{'f':'dataset'},since_rowid=100)
    arm=b.arms['dataset']
    assert arm['a']==arm['prior_a']+1
    assert arm['b']==arm['prior_b']

def test_random_exploration_advances_across_saved_bursts(tmp_path):
    p=tmp_path/'bandit.json';datasets=['d'+str(i) for i in range(100)]
    b=DatasetBandit(p);first=b.sample_arms(datasets,10);b.save()
    resumed=DatasetBandit(p);second=resumed.sample_arms(datasets,10)
    assert first != second
    assert second==b.sample_arms(datasets,10)

def test_unknown_check_evidence_is_censored_not_an_alpha_failure(tmp_path):
    db=tmp_path/'memory.db';make_db(db)
    with sqlite3.connect(db) as c:c.execute("UPDATE alpha_population SET failed_checks='CHECKS_UNVERIFIABLE'")
    b=DatasetBandit(tmp_path/'bandit.json');b.update_from_db(db,{'f':'dataset'})
    assert not b.observations and b.last_learning['unknown']==1

@pytest.mark.parametrize('failures', ['CHECKS_UNVERIFIABLE', None])
def test_previous_success_is_retracted_when_checks_become_unknown(tmp_path, failures):
    db=tmp_path/'memory.db';make_db(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE alpha_population SET is_qualified=1,failed_checks=''")
    path=tmp_path/'bandit.json'
    b=DatasetBandit(path);b.update_from_db(db,{'f':'dataset'});b.save()
    b=DatasetBandit(path)
    assert b.arms['dataset']['a']==b.arms['dataset']['prior_a']+1
    with sqlite3.connect(db) as c:
        c.execute("UPDATE alpha_population SET failed_checks=?",(failures,))
    b.update_from_db(db,{'f':'dataset'},since_rowid=100)
    assert not b.observations
    assert b.arms['dataset']['a']==b.arms['dataset']['prior_a']
    assert b.arms['dataset']['b']==b.arms['dataset']['prior_b']
    assert b.last_learning['unknown']==1 and b.last_learning['changed']==1
    b.save();reloaded=DatasetBandit(path)
    reloaded.update_from_db(db,{'f':'dataset'})
    assert reloaded.summary()==b.summary() and reloaded.last_learning['changed']==0
    with sqlite3.connect(db) as c:
        c.execute("UPDATE alpha_population SET failed_checks=''")
    reloaded.update_from_db(db,{'f':'dataset'})
    assert reloaded.arms['dataset']['a']==reloaded.arms['dataset']['prior_a']+1

@pytest.mark.parametrize('revision', [
    'UPDATE alpha_population SET fitness=NULL',
    'UPDATE alpha_population SET sharpe=NULL',
    'DELETE FROM alpha_population',
])
@pytest.mark.parametrize('success', [False, True])
def test_unscored_or_deleted_rows_are_censored_only_for_the_reconciled_database(tmp_path, revision, success):
    db=tmp_path/'memory.db';other=tmp_path/'memory.db#other'
    make_db(db);make_db(other)
    if success:
        with sqlite3.connect(db) as c:
            c.execute("UPDATE alpha_population SET is_qualified=1,failed_checks=''")
    b=DatasetBandit(tmp_path/'bandit.json')
    b.update_from_db(db,{'f':'dataset'})
    b.update_from_db(other,{'f':'other_dataset'})
    b.update('manual_dataset',True)
    preserved={k:v for k,v in b.observations.items() if k.rpartition('#')[0]==str(other.resolve())}
    with sqlite3.connect(db) as c:
        c.execute(revision)
    b.update_from_db(db,{'f':'dataset'},since_rowid=100)
    assert b.observations==preserved
    assert b.arms['dataset']['a']==b.arms['dataset']['prior_a']
    assert b.arms['dataset']['b']==b.arms['dataset']['prior_b']
    assert b.arms['other_dataset']['b']==b.arms['other_dataset']['prior_b']+1
    assert b.arms['manual_dataset']['a']==b.arms['manual_dataset']['prior_a']+1
    assert b.last_learning['scored']==0 and b.last_learning['changed']==1
    b.update_from_db(db,{'f':'dataset'})
    assert b.observations==preserved and b.last_learning['changed']==0

def test_missing_database_is_not_an_authoritative_deleted_row_snapshot(tmp_path):
    db=tmp_path/'memory.db';make_db(db)
    b=DatasetBandit(tmp_path/'bandit.json');b.update_from_db(db,{'f':'dataset'})
    before=b.summary();observations=dict(b.observations)
    db.unlink()
    assert b.update_from_db(db,{'f':'dataset'},since_rowid=100)==100
    assert b.summary()==before and b.observations==observations
