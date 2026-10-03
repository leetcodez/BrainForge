import sqlite3,json,hashlib
from forge2_offline_review import review_databases

def test_offline_review_reads_every_scored_row_without_changing_the_db(tmp_path):
    p=tmp_path/'memory.db'
    with sqlite3.connect(p) as con:
        con.execute('CREATE TABLE alpha_population(id INTEGER,expression TEXT,universe TEXT,decay INTEGER,alpha_id TEXT,sharpe REAL,turnover REAL,fitness REAL,returns REAL,is_qualified INTEGER,max_correlation REAL)')
        con.execute('CREATE TABLE alpha_checks(alpha_id TEXT,metrics_json TEXT)')
        con.execute("INSERT INTO alpha_population VALUES(1,'rank(f)','U',0,'a',2,.2,1,.15,1,.2)")
        con.execute("INSERT INTO alpha_population VALUES(2,'rank(g)','U',0,'b',3,.2,2,.15,1,.2)")
        con.execute('INSERT INTO alpha_checks VALUES(?,?)',('a',json.dumps({'checks':[{'name':'LOW_SHARPE','result':'PASS'}]})))
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    report=review_databases([p])
    assert report['scored_rows']==2
    assert report['candidates'][0]['status']=='recorded_gate_pass'
    assert report['candidates'][1]['status']=='unverifiable'
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
