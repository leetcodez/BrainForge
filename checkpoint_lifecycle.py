from pathlib import Path
import argparse,sys,json,hashlib,tempfile,types,shutil,socket
ap=argparse.ArgumentParser();ap.add_argument('--src',required=True);ap.add_argument('--artifact',required=True);ap.add_argument('--out',default='checkpoint-lifecycle-results.json');args=ap.parse_args()
sys.path.insert(0,str(Path(args.src).resolve()))
from curl_cffi.requests import Session,AsyncSession
def forbidden(*a,**k):raise AssertionError('Network prohibited')
socket.create_connection=forbidden;socket.socket.connect=forbidden;Session.request=forbidden;AsyncSession.request=forbidden
import config
from orchestrator import AlphaFactory

def new_engine(path):
 config.CHECKPOINT_PATH=str(path);obj=AlphaFactory.__new__(AlphaFactory);obj.genetic=types.SimpleNamespace(avoid_motifs=set());obj._restore_checkpoint();return obj
results={}
with tempfile.TemporaryDirectory() as td:
 root=Path(td);initial=root/'warmstart.json';src=Path(args.artifact);shutil.copyfile(src,initial)
 receipt=Path(str(src)+'.receipt.json')
 if receipt.exists():shutil.copyfile(receipt,Path(str(initial)+'.receipt.json'))
 original_hash=hashlib.sha256(initial.read_bytes()).hexdigest();engine=new_engine(initial)
 engine.population=[{'expression':expr,'universe':universe,'decay':decay} for expr,universe,decay in engine._resume_population_keys]
 same=root/'same_population_checkpoint.json';config.CHECKPOINT_PATH=str(same);engine._save_checkpoint();resumed=new_engine(same)
 checkpoint_hash=hashlib.sha256(same.read_bytes()).hexdigest()
 assert resumed.warmstart_file_hash==checkpoint_hash and resumed.warmstart_file_hash!=original_hash
 results['unchanged_population_restart']={'restored':True,'original_artifact_hash':original_hash,'retained_warmstart_hash_after_restart':resumed.warmstart_file_hash,'immutable_artifact_reference_changed':True}
 engine.population[0]['decay']=5 if engine.population[0]['decay']!=5 else 0
 changed=root/'evolved_checkpoint.json';config.CHECKPOINT_PATH=str(changed);engine._save_checkpoint()
 try:new_engine(changed)
 except ValueError as exc:results['evolved_population_restart']={'restored':False,'error':str(exc)}
 else:raise AssertionError('Expected lifecycle counterexample no longer reproduces')
 assert 'does not match manifest member' in results['evolved_population_restart']['error']
results['network_calls']=0;results['scope']='Actual supplied warmstart artifact copied to temporary fixtures; only published source used; no source or real campaign state modifications'
Path(args.out).write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
