"""Safe syntax identity and resource budgets; no speculative algebra rewrites."""
import ast,hashlib,json,math,io,tokenize
from forge2_expression import field_tokens


def expression_identity(expression):
    tree=ast.parse(expression,mode='eval')
    # Python AST removes whitespace and redundant grouping, but preserves field
    # order, signs, keyword order and constants. rank(-x) != -rank(x).
    literals=[(t.type,t.string) for t in tokenize.generate_tokens(io.StringIO(expression).readline) if t.type in (tokenize.NUMBER,tokenize.STRING)]
    return hashlib.sha256(json.dumps([ast.dump(tree,include_attributes=False),literals]).encode()).hexdigest()


def candidate_identity(payload,context):
    data={'expression_ast':expression_identity(payload['regular']),
          'settings':payload['settings'],'type':payload.get('type'),'context':context}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def budget_errors(expression,max_nodes=160,max_calls=32,max_depth=18,max_fields=8,max_window=1500):
    try:tree=ast.parse(expression,mode='eval')
    except (SyntaxError,TypeError):return ['invalid_syntax']
    nodes=list(ast.walk(tree));calls=[n for n in nodes if isinstance(n,ast.Call)]
    def depth(node):return 1+max((depth(c) for c in ast.iter_child_nodes(node)),default=0)
    errors=[]
    if len(nodes)>max_nodes:errors.append('ast_node_budget')
    if len(calls)>max_calls:errors.append('operator_call_budget')
    if depth(tree)>max_depth:errors.append('ast_depth_budget')
    if len(set(field_tokens(expression)))>max_fields:errors.append('field_count_budget')
    # Known lookback roles from the partial checker, not every numeric argument.
    from forge2_expression import _WINDOW_PARAMETERS, _GROUP_PARAMETERS
    WINDOW_SLOTS={op:parameters.index('d') if 'd' in parameters else parameters.index('lookback') for op,parameters in {**_WINDOW_PARAMETERS,'group_backfill':_GROUP_PARAMETERS['group_backfill']}.items()}
    for call in calls:
        if not isinstance(call.func,ast.Name):continue
        position=WINDOW_SLOTS.get(call.func.id.lower())
        if position is None:continue
        args=[]
        if len(call.args)>position:args.append(call.args[position])
        args.extend(k.value for k in call.keywords if k.arg in ('d','days','lookback'))
        for arg in args:
            if isinstance(arg,ast.Constant) and type(arg.value) in (int,float) and arg.value>max_window:
                errors.append('lookback_budget')
    return sorted(set(errors))
