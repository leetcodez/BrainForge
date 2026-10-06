from pathlib import Path
import tempfile,sqlite3,json,hashlib,importlib.util,contextlib,io,socket,sys,types
import argparse
ap=argparse.ArgumentParser(description='Offline counterexamples; writes only temporary fixture state and a JSON receipt.')
ap.add_argument('--src',required=True,help='Released v2 src directory')
ap.add_argument('--builder',required=True,help='Reviewed build_evidence_warmstart.py')
ap.add_argument('--out',default='review-repro-results.json')
args=ap.parse_args()
sys.path.insert(0,str(Path(args.src).resolve()))
from curl_cffi.requests import Session,AsyncSession
def blocked(*a,**k):raise AssertionError('Network forbidden')
socket.create_connection=blocked;socket.socket.connect=blocked;Session.request=blocked;AsyncSession.request=blocked
spec=importlib.util.spec_from_file_location('reviewed_builder',str(Path(args.builder).resolve()));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
from forge2_search import candidate_identity
results=[]
def setup(td,records):
 p=Path(td)/'source.db';c=sqlite3.connect(p)
 c.execute('CREATE TABLE alpha_population (id INTEGER,alpha_id TEXT,expression TEXT,universe TEXT,decay INTEGER,fitness REAL,sharpe REAL,turnover REAL,is_qualified INTEGER)')
 c.executemany('INSERT INTO alpha_population VALUES (?,?,?,?,?,?,?,?,?)',records)
 c.execute('CREATE TABLE alpha_pnl (alpha_id TEXT,date TEXT,pnl REAL)')
 c.execute('CREATE TABLE alpha_checks (alpha_id TEXT,metrics_json TEXT)');c.execute('INSERT INTO alpha_checks VALUES (?,?)',(records[0][1],'not-valid-json'));c.commit();c.close()
 m=Path(td)/'meta.json';m.write_text(json.dumps({'field_metadata':{'f':{'dataset':'earnings4','type':'MATRIX'}}}));return p,m
rows=[(1,'a','rank(f)','TOP3000',0,3.,2.,.2,0),(2,'b','rank( f )','TOP3000',0,2.,2.,.2,0),(3,'c','rank(f)','TOP3000',5,1.,2.,.2,0)]
def call(p,m,out,**kwargs):
 with contextlib.redirect_stdout(io.StringIO()):return mod.build_evidence_aware_warmstart(str(p),str(m),str(out),**kwargs)
with tempfile.TemporaryDirectory() as td:
 p,m=setup(td,rows);out=Path(td)/'warm.json';d=call(p,m,out,size=5,explore_fraction=.2)
 entries=d['warmstart_manifest']['measured_core']+d['warmstart_manifest']['unverified_exploration']
 assert entries[0]['qualification_status']=='CHECKS_VERIFIED'
 results.append({'finding':'Malformed checks promoted to CHECKS_VERIFIED','observed':entries[0]['qualification_status']})
 ids=[candidate_identity({'regular':e['expression'],'type':'REGULAR','settings':{'universe':e['universe'],'decay':e['decay']}},{'source':'fixture'}) for e in entries]
 assert len(ids)>len(set(ids));assert all(e['decay']==0 for e in entries)
 results.append({'finding':'Whitespace duplicate retained, distinct decay dropped','output_members':len(entries),'unique_evaluation_identities':len(set(ids)),'retained_decays':[e['decay'] for e in entries]})
 assert len(entries)>1
 results.append({'finding':'No-evidence fallback exceeds one-seat exploration reserve','selected':len(entries),'declared_reserve':1,'reason':d['warmstart_manifest']['basket_report']['reason']})
 before=hashlib.sha256(p.read_bytes()).hexdigest();call(p,m,p,size=2,explore_fraction=0)
 assert p.read_bytes().lstrip().startswith(b'{') and hashlib.sha256(p.read_bytes()).hexdigest()!=before
 results.append({'finding':'Output may replace the read-only source database','source_is_json_after_call':True})
with tempfile.TemporaryDirectory() as td:
 p,m=setup(td,rows);target=Path(td)/'.wq_checkpoint.json';target.write_text('{"existing":true}')
 call(p,m,target,size=2,explore_fraction=0)
 assert 'existing' not in json.loads(target.read_text())
 results.append({'finding':'Actual default checkpoint filename is not guarded','target':target.name,'existing_marker_lost':True})
with tempfile.TemporaryDirectory() as td:
 p,m=setup(td,rows);target=Path(td)/'restore.json';d=call(p,m,target,size=2,explore_fraction=0)
 import config
 from orchestrator import AlphaFactory
 config.CHECKPOINT_PATH=str(target)
 obj=AlphaFactory.__new__(AlphaFactory);obj._restore_checkpoint()
 assert obj._resume_population_keys==d['population'];assert not hasattr(obj,'warmstart_manifest')
 obj.population=[{'expression':e[0],'universe':e[1],'decay':e[2]} for e in d['population']]
 obj._save_checkpoint();saved=json.loads(target.read_text());assert 'warmstart_manifest' not in saved
 results.append({'finding':'Restore accepts keys but next checkpoint discards provenance','population_keys_restored':True,'manifest_after_save':False})
print(json.dumps({'network_calls':0,'source_changes':0,'fixture_findings':results},indent=2))
Path(args.out).write_text(json.dumps({'network_calls':0,'fixture_findings':results},indent=2))
