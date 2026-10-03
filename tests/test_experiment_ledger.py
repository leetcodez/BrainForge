import json,sqlite3
import pytest
from forge2_experiments import ExperimentLedger


def payload(expr='rank(f)',decay=0):return {'type':'REGULAR','regular':expr,'settings':{'universe':'U','decay':decay}}


def test_idempotent_semantic_identity_and_complete_settings(tmp_path):
    ledger=ExperimentLedger(tmp_path/'e.db')
    a=ledger.prepare(payload(),'context')
    assert ledger.prepare(payload('rank( f )'),'context')['attempt_id']==a['attempt_id']
    assert ledger.prepare(payload(decay=1),'context')['attempt_id']!=a['attempt_id']
    assert ledger.prepare(payload(),'other_catalog')['attempt_id']!=a['attempt_id']
    assert ledger.summary()['events']==3


def test_attempt_state_and_events_are_immutable_and_receipt_can_be_reconciled(tmp_path):
    ledger=ExperimentLedger(tmp_path/'e.db');a=ledger.prepare(payload(),'context')['attempt_id']
    ledger.dispatch(a)
    assert ledger.prepare(payload(),'context')['state']=='dispatching'
    with pytest.raises(ValueError):ledger.dispatch(a)
    with pytest.raises(ValueError):ledger.reconcile_receipt(a,'','')
    ledger.reconcile_receipt(a,'https://example.com/job','recorded response recovered')
    ledger.remote_complete(a,'alpha');ledger.complete(a,{'valid':True},{'checks':[]})
    record=ledger.prepare(payload(),'context');assert record['state']=='completed'
    assert json.loads(record['result'])['result']['valid']
    with ledger.connect() as c:
        with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM events')
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE events SET kind='fake'")
    assert ledger.summary()['events']==5


def test_dispatch_budget_is_atomic_under_concurrent_reservations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from forge2_experiments import IndeterminateAttemptError
    ledger=ExperimentLedger(tmp_path/'e.db')
    attempts=[ledger.prepare(payload(decay=i),'context')['attempt_id'] for i in range(10)]
    def reserve(a):
        try:ledger.dispatch(a,max_dispatches=3);return True
        except IndeterminateAttemptError:return False
    with ThreadPoolExecutor(10) as workers:assert sum(workers.map(reserve,attempts))==3
    assert ledger.summary()['states']=={'dispatching':3,'prepared':7}


def test_poll_deadline_and_operation_budget_survive_restart(tmp_path):
    import time
    from forge2_experiments import IndeterminateAttemptError
    ledger=ExperimentLedger(tmp_path/'e.db');a=ledger.prepare(payload(),'context')['attempt_id']
    ledger.dispatch(a);ledger.accept(a,'https://example.com/job',time.time()+60)
    ledger.reserve_poll(a,max_operations=1)
    resumed=ExperimentLedger(ledger.path)
    with pytest.raises(IndeterminateAttemptError):resumed.reserve_poll(a,max_operations=1)
    assert resumed.prepare(payload(),'context')['state']=='expired_unresolved'
    resumed.reconcile_completed_alpha(a,'recorded_alpha','completion exists in supplied archive')
    assert resumed.prepare(payload(),'context')['state']=='remote_complete'
