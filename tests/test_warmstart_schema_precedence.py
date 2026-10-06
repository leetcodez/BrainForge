"""Explicit immutable artifacts must not route through legacy runtime heuristics."""
import copy,json,shutil
from pathlib import Path
import pytest
import config
from orchestrator import AlphaFactory

@pytest.mark.parametrize('marker,value',[
    ('population_snapshot',None),
    ('decision_state',{}),
    ('pending_offspring',[]),
])
def test_explicit_warmstart_schema_cannot_bypass_validation(tmp_path,monkeypatch,marker,value):
    root=Path(__file__).resolve().parents[1]
    src=root/'evidence/evidence_aware_warmstart_v3.json'
    data=json.loads(src.read_text())
    assert data['schema_version']=='forge2-warmstart-v1'
    data['population'][0][2]=5 if data['population'][0][2]!=5 else 0
    data[marker]=value
    out=tmp_path/'original_artifact_with_runtime_hint.json'
    out.write_text(json.dumps(data))
    shutil.copyfile(Path(str(src)+'.receipt.json'),Path(str(out)+'.receipt.json'))
    monkeypatch.setattr(config,'CHECKPOINT_PATH',str(out))
    engine=AlphaFactory.__new__(AlphaFactory)
    with pytest.raises(ValueError,match='does not match manifest member'):
        engine._restore_checkpoint()
    assert not hasattr(engine,'warmstart_manifest')
    assert not hasattr(engine,'_resume_population_keys')
