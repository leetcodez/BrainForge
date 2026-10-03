"""Shared, uncapped UNIQUE tested-hypothesis accounting across campaigns.
This is a conservative observed trial count, not an estimated independent N.
"""
from __future__ import annotations
import sqlite3
import json
import hashlib
from contextlib import contextmanager
from pathlib import Path


class TrialLedger:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS trials(campaign TEXT,expression TEXT,universe TEXT,decay INTEGER,PRIMARY KEY(campaign,expression,universe,decay))')
            conn.execute('CREATE TABLE IF NOT EXISTS trial_payloads(payload_hash TEXT PRIMARY KEY,campaign TEXT,payload_json TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        conn=sqlite3.connect(self.path,timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    def record(self,campaign,expression,universe,decay,payload=None):
        with self.connect() as conn:
            conn.execute('INSERT OR IGNORE INTO trials VALUES(?,?,?,?)',(campaign,expression,universe,int(decay)))
            if payload is not None:
                raw=json.dumps(payload,sort_keys=True,allow_nan=False)
                digest=hashlib.sha256((campaign+raw).encode()).hexdigest()
                conn.execute('INSERT OR IGNORE INTO trial_payloads VALUES(?,?,?)',(digest,campaign,raw))
    def count(self):
        with self.connect() as conn:
            base=conn.execute('SELECT COUNT(*) FROM trials').fetchone()[0]
            # Additional distinct full payloads under the legacy hypothesis key
            # must increase observed N, while importing the old row does not
            # double-count the first known payload. No independence inference.
            extra=conn.execute("SELECT COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) AS n FROM trial_payloads GROUP BY campaign,json_extract(payload_json,'$.regular'),json_extract(payload_json,'$.settings.universe'),json_extract(payload_json,'$.settings.decay'))").fetchone()[0]
            return base+extra
    def import_history(self,db_path,campaign):
        if not Path(db_path).exists():return
        conn=sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True)
        try:rows=conn.execute('SELECT expression,universe,decay FROM alpha_population WHERE sharpe IS NOT NULL').fetchall()
        except sqlite3.OperationalError:rows=[]
        finally:conn.close()
        with self.connect() as out:
            out.executemany('INSERT OR IGNORE INTO trials VALUES(?,?,?,?)',[(campaign,*r) for r in rows])
