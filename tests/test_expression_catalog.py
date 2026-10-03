import json,random
import pytest
from forge2_catalog import CatalogIndex
from forge2_expression import field_tokens,type_errors,semantic_mutation,projection_mutation,window_neighbors,VECTOR_REDUCERS
from forge2_vocabulary import VocabularyBuilder

def record(fid,kind='MATRIX',dataset='a',availability=None):
    return {'id':fid,'type':kind,'dataset':dataset,'category':'fundamental','subcategory':'earnings',
            'coverage':.9,'dateCoverage':1,'alphaCount':1,'pyramidMultiplier':1.8,
            'availability':availability or [['USA',1,'U',.9,1.8,1,1]],'regions':['USA'],'delays':[1],'universes':['U']}

def catalog(tmp_path,records):
    path=tmp_path/'cat.json';path.write_text(json.dumps(records));return CatalogIndex(path)

def test_namespaces_and_vector_types_are_separate():
    assert field_tokens('vec_avg(x) + rank(y)')==('y','x') or set(field_tokens('vec_avg(x) + rank(y)'))=={'x','y'}
    meta={'x':{'type':'VECTOR'},'y':{'type':'MATRIX'}}
    assert not type_errors('vec_stddev(x)/max(abs(vec_avg(x)),0.0001)',meta)
    assert type_errors('vec_avg(y)',meta)
    assert type_errors('rank(x)',meta)
    assert type_errors('rank(missing)',meta)

def test_joint_axes_are_not_a_cartesian_product(tmp_path):
    rec=record('f',availability=[['USA',0,'U',.9,1.8,1,1],['EUR',1,'V',.9,1.2,1,1]])
    rec['regions']=['USA','EUR'];rec['delays']=[0,1];rec['universes']=['U','V']
    cat=catalog(tmp_path,[rec])
    assert cat.fields['f'].available('EUR',1,'V')
    assert not cat.fields['f'].available('EUR',0,'V')
    assert not cat.validate_expression('rank(f)','USA',0,'V')[0]
    assert cat.validate_expression('rank(f)','USA',0,'U')[0]
    assert cat.fields['f'].for_axis('EUR',1,'V').multiplier==1.2

def test_group_keys_require_the_actual_delay_and_universe(tmp_path):
    cat=catalog(tmp_path,[record('g','GROUP',availability=[['USA',0,'U',1,1,0,1]])])
    assert not cat.group_keys('USA',1,universe='U')
    assert len(cat.group_keys('USA',0,universe='U'))==1

def test_semantic_mutations_preserve_vector_input_and_dataset_locality():
    meta={'v1':{'type':'VECTOR','dataset':'a','subcategory':'s','category':'a'},
          'v2':{'type':'VECTOR','dataset':'a','subcategory':'s','category':'a'},
          'm':{'type':'MATRIX','dataset':'a','subcategory':'s','category':'a'}}
    for seed in range(100):
        expr=semantic_mutation('rank(vec_avg(v1))',meta,random.Random(seed))
        assert 'v2' in expr and 'm' not in field_tokens(expr)
        assert not type_errors(expr,meta)

def test_projection_mutation_can_reach_every_advertised_reducer():
    seen=set()
    for seed in range(100):seen.add(projection_mutation('vec_avg(v)',VECTOR_REDUCERS,random.Random(seed)).split('(')[0])
    assert seen==set(VECTOR_REDUCERS)-{'vec_avg'}

def test_deeper_fields_rotate_across_persistent_builds(tmp_path):
    cat=catalog(tmp_path,[record('f'+str(i)) for i in range(40)])
    seen=set()
    for _ in range(10):
        built=VocabularyBuilder(cat,'USA',1,{'rank','group_neutralize','ts_zscore','ts_delta','sign','subtract'}).write(tmp_path/'out')
        seen.update(fid for fid,m in built['meta']['fields'].items() if m['class']=='base')
    assert len(seen)>12
    assert len(built['rows'])<=700

def test_all_vector_projections_are_explorable_at_seed_time(tmp_path):
    cat=catalog(tmp_path,[record('v'+str(i),'VECTOR') for i in range(20)])
    seen=set()
    for seed in range(10):
        b=VocabularyBuilder(cat,'USA',1,set(VECTOR_REDUCERS)|{'rank','group_neutralize','divide','max','abs','ts_zscore','ts_delta','subtract'},rng=random.Random(seed)).build()
        seen.update(r['id'].split('(')[0] for r in b['rows'] if b['meta']['fields'][r['id']]['class']=='vector_projection')
    assert seen==set(VECTOR_REDUCERS)-{'vec_avg'}

def test_window_refinement_never_changes_backfill_or_float_guard():
    expr='divide(ts_mean(ts_backfill(f,252),60),max(abs(g),0.0001))'
    assert window_neighbors(expr,'shorter')==['divide(ts_mean(ts_backfill(f, 252), 30), max(abs(g), 0.0001))']

def test_typed_crossover_keeps_groups_vectors_and_float_guards_valid():
    from forge2_expression import typed_crossover
    meta={'v':{'type':'VECTOR'},'m':{'type':'MATRIX'},'g':{'type':'GROUP'}}
    first='group_neutralize(divide(vec_avg(v),max(abs(m),0.0001)),g)'
    second='group_rank(ts_mean(m,60),g)'
    successes=0
    for seed in range(200):
        child=typed_crossover(first,second,meta,random.Random(seed))
        if child:
            successes+=1
            assert not type_errors(child,meta)
            assert '0.0001' in child or 'divide' not in child
    assert successes>100

def test_numeric_embedding_components_are_not_tenor_spreads(tmp_path):
    cat=catalog(tmp_path,[record('embedding_component_1'),record('embedding_component_2')])
    assert not cat.term_pairs(list(cat.fields.values()))

@pytest.mark.parametrize('expression', [
    'ts_mean(m, m)', 'ts_corr(m, m, m)', 'ts_regression(m, m, d=m)',
    'ts_mean(x=m, d=rank(m))', 'ts_backfill(m, lookback=m)',
    'group_backfill(m, group=g, d=m)',
])
def test_supported_lookbacks_reject_field_valued_arguments(expression):
    meta={'m':{'type':'MATRIX'},'g':{'type':'GROUP'}}
    assert any('lookback' in error for error in type_errors(expression,meta))

@pytest.mark.parametrize('expression', [
    'group_neutralize(m, group=subindustry)',
    'group_rank(x=m, group=g)', 'group_mean(m, weight=1, group=g)',
    'group_backfill(m, group=g, d=60, std=4.0)',
    'group_backfill(x=m, group=g, d=60)',
    'ts_mean(x=m, d=60)', 'ts_corr(m, y=m, d=60)',
    'ts_backfill(m, lookback=252, k=1)',
])
def test_supported_named_arguments_bind_to_their_actual_roles(expression):
    meta={'m':{'type':'MATRIX'},'g':{'type':'GROUP'}}
    assert not type_errors(expression,meta)

@pytest.mark.parametrize('expression', [
    'group_neutralize(m, group=m)',
    'group_neutralize(m, g, group=g)',
    'ts_mean(m, 60, d=20)',
])
def test_invalid_named_group_or_duplicate_role_arguments_are_rejected(expression):
    meta={'m':{'type':'MATRIX'},'g':{'type':'GROUP'}}
    assert type_errors(expression,meta)

def test_non_window_parameters_are_not_accidentally_checked_as_lookbacks():
    meta={'m':{'type':'MATRIX'}}
    assert not type_errors('ts_target_tvr_decay(m, lambda_min=0.1, lambda_max=1, target_tvr=0.2)',meta)

@pytest.mark.parametrize('window', ['0', '-5', 'True', '1e309'])
def test_supported_lookbacks_reject_non_positive_or_non_finite_literals(window):
    assert type_errors('ts_mean(m, '+window+')',{'m':{'type':'MATRIX'}})

def test_numeric_literal_lookback_does_not_assert_undocumented_integer_coercion():
    assert not type_errors('ts_mean(m, 2.5)',{'m':{'type':'MATRIX'}})
