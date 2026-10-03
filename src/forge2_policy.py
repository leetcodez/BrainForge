"""Fingerprint effective local search/gates/settings, excluding credentials.
No platform calls. The stored policy is a compatibility contract, not certification.
"""
import hashlib,json
from pathlib import Path
from forge2_storage import atomic_json


def fingerprint(config, catalog_hash, operator_path):
    def normalize(value):
        if isinstance(value,(str,int,float,bool,type(None))):return value
        if isinstance(value,(set,frozenset)):return sorted(normalize(v) for v in value)
        if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
        if isinstance(value,dict):return {str(k):normalize(v) for k,v in sorted(value.items(),key=lambda x:str(x[0]))}
        raise TypeError
    excluded={'CHECKPOINT_PATH','SEED_POOL_PATH','WQ_BASE_URL','LLM_API_KEY','GEMINI_API_KEY',
              'OPENAI_API_KEY','ANTHROPIC_API_KEY','DATA_DICTIONARY','FIELD_GROUPS','FIELD_METADATA',
              'SEMANTIC_ACTIVE_FIELDS','FIELD_CATALOG_PATH','SESSION_CACHE_PATH','REAUTH_FLAG_PATH','SURROGATE_MODEL_PATH','MAX_DISPATCHES','MAX_POLL_OPERATIONS'}
    runtime={}
    for name,value in vars(config).items():
        if not name.isupper() or name.startswith('_') or name in excluded or any(s in name for s in ('PASSWORD','SECRET','TOKEN','API_KEY','CREDENTIAL')):continue
        try:runtime[name]=normalize(value)
        except TypeError:continue
    operators=json.loads(Path(operator_path).read_text())
    operators=sorted(operators,key=lambda op:(op.get('name',''),json.dumps(op,sort_keys=True)))
    from forge2_config import FITNESS_POLICY_VERSION
    model_path=Path(getattr(config,'SURROGATE_MODEL_PATH',''))
    model_hash=hashlib.sha256(model_path.read_bytes()).hexdigest() if model_path.is_file() else None
    policy={'model_hash':model_hash,'version':2,'source_policy':FITNESS_POLICY_VERSION,'runtime':runtime,
            'catalog_hash':catalog_hash,'operator_schema':operators,
            'settings_grid':[config.build_settings(u,d) for u in config.UNIVERSES for d in config.DECAYS]}
    digest=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return {'fingerprint':digest,'policy':policy}


def guard(path, current, database_has_rows):
    path=Path(path)
    if database_has_rows:
        if not path.exists() or json.loads(path.read_text()).get('fingerprint')!=current['fingerprint']:
            raise ValueError('Effective policy/operator/settings changed or unverified: preserve DB and migrate offline')
    atomic_json(path,current)
