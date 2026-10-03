"""Offline stress of the REAL GeneticEngine against independent syntax/leaf checks."""
import json,random,ast,socket
from curl_cffi.requests import Session,AsyncSession
network_attempts=0
def forbid_network(*args,**kwargs):
    global network_attempts
    network_attempts+=1
    raise AssertionError("Offline stress validation forbids all network calls")
socket.socket.connect=forbid_network
socket.create_connection=forbid_network
Session.request=forbid_network
AsyncSession.request=forbid_network
import config
from orchestrator import GeneticEngine
from syntax_validator import SyntaxValidator
from forge2_expression import type_errors,field_tokens
config.FIELD_METADATA={
 **{f'm{i}':{'type':'MATRIX','dataset':'d','subcategory':'s','category':'fundamental'} for i in range(6)},
 **{f'v{i}':{'type':'VECTOR','dataset':'v','subcategory':'s','category':'analyst'} for i in range(4)},
 **{f'g{i}':{'type':'GROUP','dataset':'g','subcategory':'s','category':'other'} for i in range(2)}}
config.SEMANTIC_ACTIVE_FIELDS=set(config.FIELD_METADATA)
config.SEMANTIC_MUTATION_ENABLED=True;config.VECTOR_PROJECTION_MUTATION_ENABLED=True
config.FIELD_GROUPS={'fundamental':[f'm{i}' for i in range(6)],'analyst':[f'vec_avg(v{i})' for i in range(4)]}
config.DATA_DICTIONARY=[f for fs in config.FIELD_GROUPS.values() for f in fs]
engine=GeneticEngine();random.seed(42)
pool=['group_neutralize(rank(m0),g0)','group_rank(ts_zscore(m1,60),g1)',
      'group_neutralize(divide(vec_stddev(v0),max(abs(vec_avg(v0)),0.0001)),g0)',
      'group_zscore(subtract(ts_mean(m2,20),ts_mean(m3,60)),g1)']
changed=0
for i in range(5000):
    a,b=random.sample(pool,2)
    child=engine.crossover(a,b);mutated=engine.mutate(child)
    for expr in [child,mutated]:
        ok,canon=SyntaxValidator.parse_and_validate(expr)
        assert ok and not type_errors(canon,config.FIELD_METADATA),(i,expr)
        assert set(field_tokens(expr))<=set(config.FIELD_METADATA),(i,expr)
        ast.parse(expr,mode='eval')
    changed+=mutated!=a
assert network_attempts==0
out={'iterations':5000,'validated_outputs':10000,'invalid_outputs':0,
     'changed_from_selected_parent':changed,'seed':42,'network_calls':network_attempts,
     'scope':'synthetic field metadata; structural validity, not alpha profitability'}
print(json.dumps(out,indent=2));open('evidence/fuzz-results.json','w').write(json.dumps(out,indent=2))
