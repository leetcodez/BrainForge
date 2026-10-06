from pathlib import Path
import sys,sqlite3,tempfile,json,datetime,threading,os,hashlib,socket,contextlib
import argparse
ap=argparse.ArgumentParser(description='Reproduce bounded warmstart gaps using only temporary fixtures.')
ap.add_argument('--src',required=True,help='src directory containing revised warmstart and restore modules')
ap.add_argument('--out',default='counterexample-results.json')
args=ap.parse_args()
sys.path.insert(0,str(Path(args.src).resolve()))
from curl_cffi.requests import Session,AsyncSession
def blocked(*a,**k):raise AssertionError('Network forbidden')
socket.create_connection=blocked;socket.socket.connect=blocked;Session.request=blocked;AsyncSession.request=blocked
import forge2_warmstart as w
results=[]
with tempfile.TemporaryDirectory() as td:
 r=Path(td);db=r/'source.db';con=sqlite3.connect(db)
 con.execute('CREATE TABLE alpha_population (id INTEGER,alpha_id TEXT,expression TEXT,universe TEXT,decay INTEGER,fitness REAL,sharpe REAL,turnover REAL,is_qualified INTEGER)')
 con.executemany('INSERT INTO alpha_population VALUES (?,?,?,?,?,?,?,?,?)',[(1,'a','rank(f)','TOP3000',0,3.,2.,.2,0),(2,'b','rank(vol)','TOP3000',0,2.9,2.,.2,0),(3,'c','rank(sales)','TOP3000',0,2.,2.,.2,0)])
 con.execute('CREATE TABLE alpha_pnl (alpha_id TEXT,date TEXT,pnl REAL)')
 import numpy as np
 rng=np.random.default_rng(19);a=np.cumsum(rng.normal(size=100));c=np.cumsum(rng.normal(size=100));start=datetime.date(2023,1,1)
 for aid,vals in [('a',a),('b',a),('c',c)]:con.executemany('INSERT INTO alpha_pnl VALUES (?,?,?)',[(aid,(start+datetime.timedelta(days=i)).isoformat(),float(v)) for i,v in enumerate(vals)])
 con.commit();con.close();meta=r/'meta.json';meta.write_text(json.dumps({'field_metadata':{k:{'dataset':'earnings4','type':'MATRIX'} for k in ['f','vol','sales']}}))
 out=r/'warm.json';data=w.build_evidence_aware_warmstart(str(db),str(meta),str(out),size=3,explore_fraction=.2,min_overlap=10)
 m=data['warmstart_manifest'];core=[x['alpha_id'] for x in m['measured_core']];explore=[x['alpha_id'] for x in m['unverified_exploration']]
 assert core==['a','c'] and explore==['b'];assert m['basket_report']['rejection_summary']['absolute_return_redundancy']==1
 results.append({'finding':'Known correlation clone rejected from core is re-admitted as exploration','core':core,'exploration':explore,'observed_abs_correlation':1.0})
 # The pasted restore patch stores metadata but performs no manifest or receipt validation.
 tampered=json.loads(out.read_text());tampered['population'][0][2]=5;tamper_path=r/'tampered.json';tamper_path.write_text(json.dumps(tampered))
 import config
 from orchestrator import AlphaFactory
 config.CHECKPOINT_PATH=str(tamper_path);engine=AlphaFactory.__new__(AlphaFactory);engine._restore_checkpoint()
 assert engine._resume_population_keys[0][2]==5
 results.append({'finding':'Modified population is accepted despite unchanged manifest identity and original receipt','tampered_decay_restored':5})
with tempfile.TemporaryDirectory() as td:
 target=Path(td)/'published.json';tmp=target.with_name(f'.tmp.{target.name}.{os.getpid()}');a_written=threading.Event();b_written=threading.Event();a_linked=threading.Event()
 original_write=Path.write_text;original_link=os.link;outcomes={}
 def hook_write(self,*args,**kwargs):
  val=original_write(self,*args,**kwargs)
  if self==tmp:
   if threading.current_thread().name=='A':a_written.set();assert b_written.wait(5)
   else:b_written.set();assert a_linked.wait(5)
  return val
 def hook_link(src,dst,*a,**kw):
  val=original_link(src,dst,*a,**kw)
  if Path(dst)==target and threading.current_thread().name=='A':a_linked.set()
  return val
 def publish(name):
  try:outcomes[name]={'result':'success','hash':w.exclusive_create_atomic_json(target,{'publisher':name})}
  except Exception as exc:outcomes[name]={'result':type(exc).__name__}
 Path.write_text=hook_write;os.link=hook_link
 try:
  ta=threading.Thread(target=publish,args=('A',),name='A');ta.start();assert a_written.wait(5)
  tb=threading.Thread(target=publish,args=('B',),name='B');tb.start();ta.join(8);tb.join(8);assert not ta.is_alive() and not tb.is_alive()
 finally:Path.write_text=original_write;os.link=original_link
 written=json.loads(target.read_text());assert outcomes['A']['result']=='success' and written['publisher']=='B'
 results.append({'finding':'Same-process concurrent publishers share a temporary filename; successful publisher A publishes B payload','outcomes':outcomes,'published_payload':written})
receipt={'network_calls':0,'scope':'temporary fixture state, uploaded warmstart module and isolated released dependencies with user-pasted orchestrator diff','findings':results}
Path(args.out).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
