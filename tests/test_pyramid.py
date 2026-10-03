import json
from forge2_factory import PyramidResolver

def test_unknown_fields_do_not_inherit_an_operator_multiplier(tmp_path):
    p=tmp_path/'meta.json'
    p.write_text(json.dumps({'fields':{'vec_stddev(known)':{'multiplier':1.9,'base':['known']}}}))
    r=PyramidResolver(p)
    assert r.boost('vec_stddev(unknown)') == 1.0
    assert r.boost('vec_stddev(known)') == 1.9
