"""Registered chronological research folds, disjoint final holdout, and sealing.
A local registration disciplines future work; it cannot make previously viewed
history untouched. No returns from holdout are exposed by development folds.
"""
from __future__ import annotations
import hashlib,json,datetime,sqlite3
from pathlib import Path
from forge2_storage import atomic_json


def forward_folds(dates,min_train=126,test_size=63,gap=5,holdout_size=126,label_horizon=1,max_lookback=1):
    dates=[str(d) for d in dates]
    if len(set(dates))!=len(dates) or dates!=sorted(dates):raise ValueError('Dates must be unique chronological observations')
    for d in dates:datetime.date.fromisoformat(d)
    values=[min_train,test_size,gap,holdout_size,label_horizon,max_lookback]
    if any(type(x) is not int for x in values) or min_train<30 or test_size<2 or holdout_size<2:raise ValueError('Invalid fold sizes')
    required=label_horizon-1
    if gap<required or label_horizon<1 or max_lookback<1:raise ValueError('Gap must cover registered outcome horizon minus one')
    holdout_start=len(dates)-holdout_size
    development_stop=holdout_start-gap
    train_start=max_lookback-1
    if development_stop<train_start+min_train+gap+test_size:raise ValueError('Insufficient history for development folds and separated holdout')
    folds=[];test_start=train_start+min_train+gap
    while test_start+test_size<=development_stop:
        train_stop=test_start-gap
        folds.append({'train':[train_start,train_stop],'test':[test_start,test_start+test_size],
                      'train_last':dates[train_stop-1],'test_first':dates[test_start]})
        test_start+=test_size
    return {'version':1,'dates_sha256':hashlib.sha256(json.dumps(dates).encode()).hexdigest(),
            'observations':len(dates),'folds':folds,'development':[0,development_stop],
            'holdout':[holdout_start,len(dates)],'holdout_dates':dates[holdout_start:],'holdout_gap':[development_stop,holdout_start],
            'warmup':[0,train_start],'gap':gap,'max_lookback':max_lookback,'label_horizon':label_horizon,
            'index_semantics':'half-open chronological observation indices',
            'caveat':'Conservative forward split; not general interval-label purging or CPCV. Register before tuning. Previously viewed history is not restored to untouched status.'}


def register_protocol(path,plan,data_hash,search_policy_hash,previously_viewed=True,data_exposure_namespace=None):
    path=Path(path)
    if not previously_viewed and not data_exposure_namespace:raise ValueError("Untouched-holdout claim requires an explicit stable exposure namespace, never a re-encoding-sensitive artifact hash")
    if path.exists():raise ValueError('Protocol is immutable; create a new research registration instead of overwriting it')
    record={'plan':plan,'data_hash':data_hash,'search_policy_hash':search_policy_hash,
            'previously_viewed':bool(previously_viewed),'data_exposure_namespace':data_exposure_namespace or data_hash,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    digest=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()
    record['protocol_hash']=digest
    # Exclusive creation prevents two registrations racing past the check.
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as fh:json.dump(record,fh,indent=2);fh.flush();__import__('os').fsync(fh.fileno())
    return record


class HoldoutSeal:
    """Single recorded final evaluation; state remains consumed after a crash.
    Caller must verify the artifact hash and submit an already frozen candidate.
    Prevents silent repeat calls through this API, not access outside the API.
    """
    def __init__(self,path):self.path=Path(path)
    def evaluate(self,registration,frozen_candidate_hash,data_hash,evaluator):
        unsigned={k:v for k,v in registration.items() if k!='protocol_hash'}
        if hashlib.sha256(json.dumps(unsigned,sort_keys=True).encode()).hexdigest()!=registration['protocol_hash']:raise ValueError('Registration was modified')
        if data_hash!=registration['data_hash']:raise ValueError('Registered data identity changed')
        if registration['previously_viewed']:raise ValueError('Already viewed history cannot be labeled untouched holdout')
        if not frozen_candidate_hash:raise ValueError('Freeze candidate/portfolio before holdout')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(self.path,timeout=30)
        try:
            with conn:
                conn.execute('CREATE TABLE IF NOT EXISTS seals(protocol_hash TEXT PRIMARY KEY,candidate_hash TEXT,status TEXT,result TEXT)')
                conn.execute('CREATE TABLE IF NOT EXISTS exposed_observations(namespace TEXT,observation_id TEXT,protocol_hash TEXT,PRIMARY KEY(namespace,observation_id))')
                try:
                    conn.executemany('INSERT INTO exposed_observations VALUES(?,?,?)',
                        [(registration['data_exposure_namespace'],d,registration['protocol_hash']) for d in registration['plan']['holdout_dates']])
                    conn.execute('INSERT INTO seals VALUES(?,?,?,NULL)',(registration['protocol_hash'],frozen_candidate_hash,'claimed'))
                except sqlite3.IntegrityError:raise ValueError('Holdout observations already exposed/claimed; changing registration/candidate/policy cannot reset them')
            result=evaluator(registration['plan']['holdout'])
            raw=json.dumps(result,allow_nan=False)
            with conn:conn.execute('UPDATE seals SET status=?,result=? WHERE protocol_hash=?',('completed',raw,registration['protocol_hash']))
            return result
        finally:conn.close()


def purge_forward_events(events,test_indices):
    """Inclusive information intervals and explicit as-of availability.
    Strictly forward: post-test embargo is inapplicable to past-only training.
    Trailing feature warmup is separate from label overlap; this is not CPCV.
    """
    def instant(value):
        t=datetime.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t.replace(tzinfo=datetime.timezone.utc) if t.tzinfo is None else t
    if not test_indices or any(type(i) is not int or i<0 or i>=len(events) for i in test_indices):raise ValueError('Invalid test membership')
    parsed=[]
    for row in events:
        times={k:instant(row[k]) for k in ('decision_time','outcome_start','outcome_end','label_available_at','feature_available_at')}
        if not times['decision_time']<=times['outcome_start']<=times['outcome_end']<=times['label_available_at']:raise ValueError('Invalid outcome information interval')
        parsed.append(times)
    if any(parsed[i]['decision_time']>=parsed[i+1]['decision_time'] for i in range(len(parsed)-1)):raise ValueError('Decisions must be strictly chronological')
    test=set(test_indices)
    if any(parsed[i]['feature_available_at']>parsed[i]['decision_time'] for i in test):raise ValueError('Validation event has future feature availability')
    cutoff=min(parsed[i]['decision_time'] for i in test)
    spans=[(parsed[i]['outcome_start'],parsed[i]['outcome_end']) for i in test]
    train=[];excluded={}
    for i,row in enumerate(parsed):
        if i in test:continue
        if row['decision_time']>=cutoff:reason='not_strictly_forward'
        elif row['feature_available_at']>row['decision_time']:reason='feature_not_available_as_of_decision'
        elif any(row['outcome_start']<=stop and row['outcome_end']>=begin for begin,stop in spans):reason='overlapping_outcome_information'
        elif row['label_available_at']>=cutoff:reason='label_not_available_at_train_cutoff'
        else:train.append(i);continue
        excluded[str(i)]=reason
    return {'train_indices':train,'test_indices':sorted(test),'excluded':excluded,'intervals':'closed/inclusive',
            'caveat':'Truthful source timestamps required; cannot repair globally selected candidate-pool leakage'}
