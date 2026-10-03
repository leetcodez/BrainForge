import json,os,subprocess,sys
import datetime
from submission_scout import _greedy_order
from forge2_factory import PyramidResolver

def test_actual_import_time_loader_isolated_from_static_fields(tmp_path):
    cat=tmp_path/'data_fields.json';cat.write_text(json.dumps([
        {'id':'only_field','type':'MATRIX','category':'fundamental','priorityScore':1,'coverageMode':'direct'},
        {'id':'vec_stddev(v)','type':'MATRIX','category':'fundamental','priorityScore':.9,'coverageMode':'direct'}]))
    env=dict(os.environ,WQ_VOCAB_ISOLATED='1',WQ_FIELD_CATALOG=str(cat),WQ_HARVEST_VOCAB_MAX='900')
    output=subprocess.check_output([sys.executable,'-c',"import config,json;print(json.dumps(config.DATA_DICTIONARY))"],env=env,text=True)
    assert json.loads(output.strip())==['only_field','vec_stddev(v)']

def test_scout_does_not_recommend_a_pair_with_unknown_overlap():
    passing=[{'alpha_id':'a','fitness':2},{'alpha_id':'b','fitness':1}]
    def changes(year):return {(datetime.date(year,1,1)+datetime.timedelta(days=i)).isoformat():float(i%7) for i in range(100)}
    tier_a,tier_b=_greedy_order(passing,{'a':changes(2020),'b':changes(2022)})
    assert len(tier_a)==1 and len(tier_b)==1 and tier_b[0][1] is None

def test_pyramid_proxy_uses_exact_axis_and_cannot_ignore_unknown_leaves(tmp_path):
    p=tmp_path/'meta.json';p.write_text(json.dumps({'axes':{'region':'USA','delay':1},
      'field_metadata':{'f':{'type':'MATRIX','multiplier':1.9,'availability':[['USA',1,'U',.9,1.2,1,1],['USA',1,'V',.9,1.9,1,1]]}}}))
    r=PyramidResolver(p)
    assert r.boost('rank(f)','U')==1.2
    assert r.boost('rank(f)','V')==1.9
    assert r.boost('rank(f+unknown)','V')==1


def test_scout_unknown_correlation_values_do_not_become_passes():
    import asyncio
    from submission_scout import _self_correlation
    class Fixture:
        def __init__(self,value):self.value=value
        async def request(self,*a):return {'status_code':200,'json':self.value}
    async def exercise():
        for body in [{'max':float('nan')},{'max':2},{'max':True},{'records':[{'correlation':.1},{'correlation':'unknown'}]}]:
            assert await _self_correlation(Fixture(body),'a') is None
        assert await _self_correlation(Fixture({'records':[]}),'a')==0
    asyncio.run(exercise())
