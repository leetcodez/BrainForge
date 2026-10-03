"""Pure expression semantics: separate function/field namespaces and typed grafts.
This is a conservative partial type checker, NOT a replacement for FastExpr.
"""
from __future__ import annotations
import ast
import copy
import math
import random
from collections import Counter
from typing import Mapping

BUILTIN_GROUPS = frozenset({'SUBINDUSTRY','INDUSTRY','SECTOR','MARKET','subindustry','industry','sector','market'})
VECTOR_REDUCERS = ('vec_avg','vec_count','vec_max','vec_min','vec_range','vec_stddev','vec_sum')

# Deliberately limited to documented roles from the saved operator signatures.
# This is not a complete FastExpr signature/type registry. Unknown operators
# retain the partial scalar/vector checks below.
_WINDOW_PARAMETERS = {
    op: ('x', 'd') for op in (
        'ts_zscore', 'ts_product', 'ts_std_dev', 'ts_sum', 'ts_av_diff',
        'ts_kurtosis', 'ts_mean', 'ts_arg_max', 'ts_ir', 'ts_delay',
        'ts_count_nans', 'ts_arg_min', 'ts_max_diff', 'ts_delta',
    )
}
_WINDOW_PARAMETERS.update({
    'ts_corr': ('x', 'y', 'd'),
    'ts_covariance': ('y', 'x', 'd'),
    'ts_regression': ('y', 'x', 'd', 'lag', 'rettype'),
    'ts_returns': ('x', 'd', 'mode'),
    'ts_scale': ('x', 'd', 'constant'),
    'ts_rank': ('x', 'd', 'constant'),
    'ts_quantile': ('x', 'd', 'driver'),
    'ts_decay_linear': ('x', 'd', 'dense'),
    'ts_backfill': ('x', 'lookback', 'k'),
})
_GROUP_PARAMETERS = {
    op: ('x', 'group') for op in (
        'group_rank', 'group_scale', 'group_count', 'group_zscore',
        'group_std_dev', 'group_sum', 'group_neutralize',
    )
}
_GROUP_PARAMETERS.update({
    'group_mean': ('x', 'weight', 'group'),
    'group_backfill': ('x', 'group', 'd', 'std'),
})


def _bind_roles(node, parameters, errors):
    """Bind supported positional/named slots without guessing unknown roles."""
    op = node.func.id.lower()
    bound = dict(zip(parameters, node.args))
    if len(node.args) > len(parameters):
        errors.append(op + ' has too many positional arguments')
    for kw in node.keywords:
        name = kw.arg
        if name not in parameters:
            errors.append(op + ' has unsupported named argument: ' + str(kw.arg))
        elif name in bound:
            errors.append(op + ' has duplicate argument: ' + name)
        else:
            bound[name] = kw.value
    return bound


def _numeric_lookback(node):
    # Positive finite numeric literals are supported; do not infer dynamic
    # windows from MATRIX values or assert undocumented integer coercion rules.
    if not isinstance(node, ast.Constant):
        return False
    if type(node.value) is int:
        return node.value > 0
    return type(node.value) is float and math.isfinite(node.value) and node.value > 0


def field_tokens(expression: str) -> tuple[str, ...]:
    """Names in operand positions only; function identifiers are never fields."""
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, TypeError):
        return ()
    functions = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return tuple(n.id for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and id(n) not in functions)


def type_errors(expression: str, metadata: Mapping[str, dict]) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, TypeError):
        return ['invalid expression syntax']

    def infer(node):
        if isinstance(node, ast.Name):
            if node.id in BUILTIN_GROUPS:
                return 'GROUP'
            meta = metadata.get(node.id)
            if meta is None:
                errors.append('unknown field: ' + node.id)
                return 'UNKNOWN'
            return str(meta.get('type', 'MATRIX')).upper()
        if isinstance(node, ast.Constant):
            return 'LITERAL' if isinstance(node.value, str) else 'MATRIX'
        if isinstance(node, ast.List):
            for elt in node.elts:
                infer(elt)
            return 'LITERAL'
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                errors.append('indirect function calls are forbidden')
                return 'UNKNOWN'
            op = node.func.id.lower()
            kinds = [infer(arg) for arg in node.args]
            keyword_kinds = [infer(kw.value) for kw in node.keywords]
            parameters = _WINDOW_PARAMETERS.get(op) or _GROUP_PARAMETERS.get(op)
            bound = {}
            if parameters:
                bound = _bind_roles(node, parameters, errors)
                if op in _WINDOW_PARAMETERS or op == 'group_backfill':
                    window_name = 'lookback' if op == 'ts_backfill' else 'd'
                    if not _numeric_lookback(bound.get(window_name)):
                        errors.append(op + ' requires a positive numeric literal lookback')
            if op in VECTOR_REDUCERS:
                if len(kinds) != 1 or kinds[0] != 'VECTOR':
                    errors.append(op + ' requires one VECTOR operand')
                return 'MATRIX'
            if op == 'densify':
                if len(kinds)!=1 or kinds[0]!='GROUP':errors.append('densify requires a GROUP operand')
                return 'GROUP'
            if op == 'bucket':
                if kinds and kinds[0] not in ('MATRIX', 'UNKNOWN'):
                    errors.append('bucket requires a scalar operand')
                return 'GROUP'
            if op in _GROUP_PARAMETERS:
                group = bound.get('group')
                if group is None or infer(group) != 'GROUP':
                    errors.append(op + ' requires a GROUP key')
                for name, arg in bound.items():
                    if name != 'group' and infer(arg) in ('VECTOR', 'GROUP'):
                        errors.append(op + ' requires scalar signal operands')
            elif op.startswith('group_'):
                group_at = 1 if op == 'group_backfill' else len(kinds)-1
                if group_at < 0 or kinds[group_at] != 'GROUP':
                    errors.append(op + ' requires a GROUP key')
                for i,k in enumerate(kinds):
                    if i != group_at and k in ('VECTOR','GROUP'):
                        errors.append(op + ' requires scalar signal operands')
            elif any(k in ('VECTOR','GROUP') for k in kinds + keyword_kinds):
                errors.append(op + ' requires scalar operands')
            return 'MATRIX'
        if isinstance(node, (ast.BinOp,ast.UnaryOp,ast.Compare)):
            children = [c for c in ast.iter_child_nodes(node)
                        if isinstance(c,(ast.Call,ast.Name,ast.Constant,ast.BinOp,ast.UnaryOp,ast.Compare))]
            if any(infer(c) in ('VECTOR','GROUP') for c in children):
                errors.append('arithmetic/comparison requires scalar operands')
            return 'MATRIX'
        errors.append('unsupported expression node: '+type(node).__name__)
        return 'UNKNOWN'
    infer(tree.body)
    return list(dict.fromkeys(errors))


def semantic_mutation(expression: str, metadata: Mapping[str,dict], rng=None) -> str | None:
    """Replace a real field leaf with a same-type semantic neighbor via AST.
    60% subcategory / 30% dataset / 10% category; fallback widens only by type.
    VECTOR leaves remain VECTOR leaves (never graft scalar projections inside
    reducers); GROUP leaves are only replaced with GROUP leaves.
    """
    rng = rng or random
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        return None
    funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)}
    slots = [n for n in ast.walk(tree) if isinstance(n,ast.Name)
             and id(n) not in funcs and n.id in metadata]
    if not slots:
        return None
    target = rng.choice(slots)
    source = metadata[target.id]
    candidates = [(fid,m) for fid,m in metadata.items()
                  if fid != target.id and m.get('type') == source.get('type')]
    if not candidates:
        return None
    roll = rng.random()
    levels = ['subcategory','dataset','category'] if roll < .6 else (
        ['dataset','subcategory','category'] if roll < .9 else ['category','dataset','subcategory'])
    pool = []
    for level in levels:
        value = source.get(level)
        pool = [fid for fid,m in candidates if value and m.get(level)==value
                and (level != 'subcategory' or m.get('dataset')==source.get('dataset'))]
        if pool:
            break
    if not pool:
        pool = [fid for fid,_ in candidates]
    replacement = ast.parse(rng.choice(pool), mode='eval').body
    class Graft(ast.NodeTransformer):
        def visit_Name(self,node):
            return ast.copy_location(copy.deepcopy(replacement),node) if node is target else node
    tree=Graft().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def projection_mutation(expression: str, allowed_ops, rng=None) -> str | None:
    rng = rng or random
    try:
        tree=ast.parse(expression,mode='eval')
    except SyntaxError:
        return None
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Name) and n.func.id in VECTOR_REDUCERS]
    if not nodes:
        return None
    node=rng.choice(nodes)
    alternatives=[op for op in VECTOR_REDUCERS if op in allowed_ops and op != node.func.id]
    if not alternatives:
        return None
    node.func.id=rng.choice(alternatives)
    return ast.unparse(tree)


def window_neighbors(expression: str, direction: str) -> list[str]:
    """Target documented numeric lookback slots; never mutate float boundaries."""
    slots={op:1 for op in ['ts_rank','ts_zscore','ts_mean','ts_delta','ts_std_dev','ts_decay_linear','ts_av_diff']}
    slots.update({'ts_corr':2,'ts_covariance':2,'ts_regression':2})
    tree=ast.parse(expression,mode='eval');out=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name):continue
        idx=slots.get(node.func.id)
        if idx is None or len(node.args)<=idx:continue
        arg=node.args[idx]
        if not isinstance(arg,ast.Constant) or type(arg.value) is not int or arg.value<2:continue
        old=arg.value
        new=max(2,round(old*(.5 if direction=='shorter' else 1.5)))
        if new==old:continue
        arg.value=new;out.append(ast.unparse(tree));arg.value=old
    return list(dict.fromkeys(out))


def typed_crossover(expr1: str, expr2: str, metadata, rng=None, max_depth=20) -> str | None:
    """Graft compatible operand subtrees; exclude functions and literal guards."""
    rng=rng or random
    try:
        base=ast.parse(expr1,mode='eval');other=ast.parse(expr2,mode='eval')
    except SyntaxError:return None
    def kind(n):
        if isinstance(n,ast.Name):
            return 'GROUP' if n.id in BUILTIN_GROUPS else metadata.get(n.id,{}).get('type','UNKNOWN')
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('bucket','densify'):return 'GROUP'
        if isinstance(n,ast.Constant):return 'WINDOW' if type(n.value) is int and n.value>=2 else 'LITERAL'
        return 'MATRIX'
    funcs={id(n.func) for n in ast.walk(other) if isinstance(n,ast.Call)}
    donors=[n for n in ast.walk(other) if isinstance(n,(ast.Name,ast.Call,ast.BinOp,ast.UnaryOp,ast.Compare,ast.Constant))
            and id(n) not in funcs and kind(n) not in ('LITERAL','UNKNOWN')]
    for _ in range(12):
        tree=copy.deepcopy(base);slots=[]
        protected=set()
        for call in ast.walk(tree):
            if (isinstance(call,ast.Call) and isinstance(call.func,ast.Name)
                    and call.func.id=='divide' and len(call.args)==2
                    and any(isinstance(n,ast.Constant) and type(n.value) is float
                            for n in ast.walk(call.args[1]))):
                protected.update(id(n) for n in ast.walk(call.args[1]))
        for parent in ast.walk(tree):
            for name,value in ast.iter_fields(parent):
                if name=='func':continue
                if isinstance(value,list):
                    for i,node in enumerate(value):
                        if isinstance(node,(ast.Name,ast.Call,ast.BinOp,ast.UnaryOp,ast.Compare,ast.Constant)) and kind(node) not in ('LITERAL','UNKNOWN') and id(node) not in protected:
                            slots.append((parent,name,i,node))
                elif isinstance(value,(ast.Name,ast.Call,ast.BinOp,ast.UnaryOp,ast.Compare,ast.Constant)) and kind(value) not in ('LITERAL','UNKNOWN') and id(value) not in protected:
                    slots.append((parent,name,None,value))
        if not slots:return None
        parent,name,index,target=rng.choice(slots)
        pool=[n for n in donors if kind(n)==kind(target)]
        if isinstance(parent,ast.Expression):pool=[n for n in pool if isinstance(n,(ast.Call,ast.BinOp,ast.UnaryOp,ast.Compare))]
        if not pool:continue
        donor=copy.deepcopy(rng.choice(pool))
        if index is None:setattr(parent,name,donor)
        else:getattr(parent,name)[index]=donor
        ast.fix_missing_locations(tree)
        def depth(n):return 1+max((depth(c) for c in ast.iter_child_nodes(n)),default=0)
        expr=ast.unparse(tree)
        if depth(tree)<=max_depth and not type_errors(expr,metadata):return expr
    return None
