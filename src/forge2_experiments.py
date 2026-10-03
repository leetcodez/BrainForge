"""Durable local attempt state plus immutable events.
Cannot make a remote POST and local SQLite commit atomic. A dispatch with no
receipt is indeterminate and requires reconciliation, never an automatic repost.
"""
from __future__ import annotations
import datetime,json,sqlite3,uuid,time
from contextlib import contextmanager
from pathlib import Path
from forge2_search import candidate_identity


class IndeterminateAttemptError(RuntimeError):pass


class ExperimentLedger:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS candidates(candidate_id TEXT PRIMARY KEY,payload TEXT NOT NULL,context TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS attempts(attempt_id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL UNIQUE,state TEXT NOT NULL,receipt TEXT,result TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY,attempt_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL)')
            c.execute("CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")
            c.execute("CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
        c.execute('PRAGMA busy_timeout=30000');c.execute('PRAGMA synchronous=FULL')
        try:
            with c:yield c
        finally:c.close()
    @staticmethod
    def _event(c,attempt,kind,body):
        c.execute('INSERT INTO events(attempt_id,kind,body,created_at) VALUES(?,?,?,?)',
            (attempt,kind,json.dumps(body,sort_keys=True,allow_nan=False),datetime.datetime.now(datetime.timezone.utc).isoformat()))
    def prepare(self,payload,context,lineage=None):
        cid=candidate_identity(payload,context)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?)',(cid,json.dumps(payload,sort_keys=True,allow_nan=False),json.dumps(context,sort_keys=True,allow_nan=False)))
            row=c.execute('SELECT * FROM attempts WHERE candidate_id=?',(cid,)).fetchone()
            if row is None:
                aid=uuid.uuid4().hex
                c.execute('INSERT INTO attempts VALUES(?,?,?,NULL,NULL)',(aid,cid,'prepared'))
                self._event(c,aid,'prepared',{'candidate_id':cid,'lineage':lineage or {}})
                row=c.execute('SELECT * FROM attempts WHERE attempt_id=?',(aid,)).fetchone()
            return dict(row)
    def transition(self,attempt,expected,state,body=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM attempts WHERE attempt_id=?',(attempt,)).fetchone()
            if row is None or row['state'] not in expected:raise ValueError('Invalid or concurrent attempt transition')
            receipt=row['receipt'];result=row['result']
            if state in ('accepted','remote_complete'):receipt=json.dumps(body,allow_nan=False)
            if state=='completed':result=json.dumps(body,allow_nan=False)
            c.execute('UPDATE attempts SET state=?,receipt=?,result=? WHERE attempt_id=?',(state,receipt,result,attempt))
            self._event(c,attempt,state,body or {})
    def dispatch(self,attempt,max_dispatches=0):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state FROM attempts WHERE attempt_id=?',(attempt,)).fetchone()
            if row is None or row['state']!='prepared':raise ValueError('Invalid/concurrent dispatch transition')
            used=c.execute("SELECT COUNT(*) FROM events WHERE kind='dispatching'").fetchone()[0]
            if max_dispatches and used>=max_dispatches:raise IndeterminateAttemptError('Local dispatch budget exhausted; prepared candidate not sent')
            c.execute("UPDATE attempts SET state='dispatching' WHERE attempt_id=?",(attempt,))
            self._event(c,attempt,'dispatching',{'dispatch_index':used+1})
    def accept(self,attempt,poll_url,deadline_epoch=None):
        if not poll_url:raise ValueError('Accepted attempt requires a poll receipt')
        self.transition(attempt,{'dispatching'},'accepted',{'poll_url':poll_url,'deadline_epoch':deadline_epoch})
    def reserve_poll(self,attempt,max_operations=1000):
        expired=False
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM attempts WHERE attempt_id=?',(attempt,)).fetchone()
            if row is None or row['state']!='accepted':raise IndeterminateAttemptError('No accepted pollable attempt')
            receipt=json.loads(row['receipt']);deadline=receipt.get('deadline_epoch')
            count=c.execute("SELECT COUNT(*) FROM events WHERE attempt_id=? AND kind='poll_reserved'",(attempt,)).fetchone()[0]
            expired=(deadline is None or time.time()>=deadline or count>=max_operations)
            if expired:
                c.execute("UPDATE attempts SET state='expired_unresolved' WHERE attempt_id=?",(attempt,))
                self._event(c,attempt,'expired_unresolved',{'reason':'missing/expired deadline or poll-operation budget','operations':count})
            else:self._event(c,attempt,'poll_reserved',{'index':count+1})
        if expired:raise IndeterminateAttemptError('Polling deadline/budget closed; remote work unresolved, do not repost')

    def reconcile_completed_alpha(self,attempt,alpha_id,reason):
        if not alpha_id or not reason:raise ValueError('Recorded completed alpha ID and reconciliation reason required')
        self.transition(attempt,{'dispatching','expired_unresolved'},'remote_complete',{'alpha_id':alpha_id,'reconciliation_reason':reason})

    def remote_complete(self,attempt,alpha_id):
        if not alpha_id:raise ValueError('Missing completed alpha ID')
        self.transition(attempt,{'accepted'},'remote_complete',{'alpha_id':alpha_id})
    def complete(self,attempt,result,metrics):self.transition(attempt,{'remote_complete'},'completed',{'result':result,'metrics':metrics})
    def reject(self,attempt,reason):self.transition(attempt,{'dispatching','accepted'},'failed',{'reason':reason})
    def reconcile_receipt(self,attempt,poll_url,reason,deadline_epoch=None):
        if not poll_url or not reason:raise ValueError('Recorded receipt and reconciliation reason required')
        self.transition(attempt,{'dispatching'},'accepted',{'poll_url':poll_url,'reconciliation_reason':reason,'deadline_epoch':deadline_epoch})
    def summary(self):
        with self.connect() as c:
            return {'states':{r['state']:r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM attempts GROUP BY state')},
                    'events':c.execute('SELECT COUNT(*) FROM events').fetchone()[0],
                    'caveat':'dispatching without a receipt is indeterminate, not a failed alpha or permission to retry'}
