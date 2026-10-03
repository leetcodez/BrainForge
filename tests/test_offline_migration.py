import hashlib,json,sqlite3
from pathlib import Path
from db_manager import DatabaseManager
from forge2_migrate_offline import migrate

def test_offline_migration_preserves_source_and_censors_missing_checks(tmp_path):
    source=tmp_path/'original.db';db=DatabaseManager(str(source));db.init_db_sync()
    db.save_alpha_sync('rank(f1)','U',0,'old_alpha',0,2,.2,1,4,returns=.15,is_qualified=1,failed_checks='',max_correlation=.2)
    db.close_sync();before=hashlib.sha256(source.read_bytes()).hexdigest()
    cat=tmp_path/'catalog.json';cat.write_text(json.dumps([{'id':'f1','type':'MATRIX','dataset':'d','category':'fundamental','coverage':.9,'dateCoverage':1,'alphaCount':1,
      'regions':['USA'],'delays':[1],'universes':['U'],'availability':[['USA',1,'U',.9,1.5,1,1]]}]))
    operators=Path(__file__).resolve().parents[1]/'src/operators.json'
    out=tmp_path/'migrated';receipt=migrate(source,cat,operators,out)
    assert receipt['rescored_rows']==1 and receipt['warmstart_members']==1 and receipt['unknown_check_rows']==1
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    with sqlite3.connect(out/'brain_memory.db') as con:
        row=con.execute('SELECT legacy_fitness,is_qualified,failed_checks FROM alpha_population').fetchone()
    assert row==(1.,0,'CHECKS_UNVERIFIABLE')
    assert json.loads((out/'checkpoint.json').read_text())['population']==[['rank(f1)','U',0]]
    assert (out/'migration_receipt.json').exists()


def test_migrated_policy_matches_fresh_engine_process(tmp_path):
    import os,subprocess,sys
    import forge2_config as F2
    source=tmp_path/'original.db';db=DatabaseManager(str(source));db.init_db_sync()
    db.save_alpha_sync('rank(f1)','U',0,'a',0,2,.2,1,4,returns=.15)
    db.close_sync()
    cat=tmp_path/'catalog.json';cat.write_text(json.dumps([{'id':'f1','type':'MATRIX','dataset':'d','category':'fundamental','coverage':.9,'dateCoverage':1,'alphaCount':1,
      'regions':['USA'],'delays':[1],'universes':['U'],'availability':[['USA',1,'U',.9,1.5,1,1]]}]))
    root=Path(__file__).resolve().parents[1];ops=root/'src/operators.json';out=tmp_path/'migrated'
    migrate(source,cat,ops,out)
    manifest=json.loads((out/'forge2_epoch_manifest.json').read_text());epoch=out/manifest['epoch_dir']
    env={**os.environ,**F2.OVERRIDE_ENV,'PYTHONPATH':str(root/'src'),'WQ_FIELD_CATALOG':str(epoch/'data_fields.json'),
         'WQ_SEED_POOL':str(epoch/'seed_pool.json'),'WQ_OPERATORS_PATH':str(ops),'BRAINFORGE_DB':str(out/'brain_memory.db'),
         'WQ_CHECKPOINT':str(out/'checkpoint.json'),'FORGE2_POLICY_PATH':str(out/'forge2_run_policy.json')}
    script="""
import socket
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden'))
import config,orchestrator
class NoNetwork:
    def __init__(self):pass
orchestrator.NetworkEngine=NoNetwork
from forge2_factory import apply_config_overrides,build_factory
apply_config_overrides(config,'USA',1)
import sys
factory=build_factory(sys.argv[1])
print('fresh policy matched; no network object used')
"""
    result=subprocess.run([sys.executable,'-c',script,str(epoch/'forge2_field_meta.json')],env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
