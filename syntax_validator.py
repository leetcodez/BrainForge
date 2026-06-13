import ast
import copy
import logging
import re
from functools import lru_cache

import config

logger = logging.getLogger(__name__)

# Concrete field -> its data group, used to abstract expressions into structural
# MOTIFS (fields collapsed to their group, constants to a generic token).
_FIELD_TO_GROUP = {}
for _g, _fs in config.FIELD_GROUPS.items():
    for _f in _fs:
        _FIELD_TO_GROUP[_f] = _g


def _get_field_to_group():
    """Concrete-field -> data-group lookup used by structural_motifs() to abstract
    expressions into MOTIFS (fields collapsed to their group). Returns the
    module-level map built from config.FIELD_GROUPS at import time -- after any
    dataset-scoped harvest swap has already finalized FIELD_GROUPS, so the map is
    correct for both broad and dataset-scoped runs. Exposed as a function because
    structural_motifs() calls _get_field_to_group(); without this definition every
    motif / originality / FSA-avoidance call raised NameError."""
    return _FIELD_TO_GROUP


class AlphaSyntaxValidator(ast.NodeVisitor):
    def __init__(self):
        self.allowed_nodes = {
            ast.Module,
            ast.Expression,
            ast.Expr,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.USub,
            ast.UAdd,
            ast.Constant,
            ast.List,
            ast.keyword,
            ast.Compare,
            ast.Gt,
            ast.GtE,
            ast.Lt,
            ast.LtE,
            ast.Eq,
            ast.NotEq,
        }
        self.allowed_operators = {op.lower() for op in config.ALLOWED_OPERATORS}

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise ValueError(f"Forbidden AST node type: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct FastExpr function calls are allowed")

        func_name = node.func.id.lower()
        if func_name not in self.allowed_operators:
            raise ValueError(f"Forbidden function call: {func_name}")

        arg_count = len(node.args) + len(node.keywords)
        if not SyntaxValidator.operator_accepts_arity(func_name, arg_count):
            min_args, max_args = config.OPERATOR_ARITY.get(func_name, (0, None))
            expected = f"{min_args}+" if max_args is None else f"{min_args}-{max_args}"
            raise ValueError(f"Invalid arity for {func_name}: got {arg_count}, expected {expected}")

        self.generic_visit(node)


# OPTIMIZATION: Cache parsed AST trees to avoid re-parsing
@lru_cache(maxsize=8192)
def _parse_expression(expression: str):
    """Parse and cache AST trees to avoid re-parsing the same expression.
    
    Expressions are parsed multiple times across validation, canonicalization,
    motif extraction, and mutation. This cache eliminates the redundancy.
    """
    return ast.parse(expression, mode="eval")

@lru_cache(maxsize=8192)
def _canonicalize_cached(expression: str) -> str:
    """Pure, cacheable canonicalization. Raises on unparseable input."""
    tree = _parse_expression(expression)

    class CanonicalTransformer(ast.NodeTransformer):
        def visit_BinOp(self, node):
            node = self.generic_visit(node)
            if isinstance(node.op, SyntaxValidator.COMMUTATIVE_BINOPS):
                operands = self._flatten_binop(node, type(node.op))
                operands.sort(key=ast.unparse)
                return self._build_binop(operands, type(node.op))
            return node

        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id.lower() in SyntaxValidator.COMMUTATIVE_FUNCTIONS:
                node.args = sorted(node.args, key=ast.unparse)
            return node

        def _flatten_binop(self, node, op_type):
            if isinstance(node, ast.BinOp) and isinstance(node.op, op_type):
                return self._flatten_binop(node.left, op_type) + self._flatten_binop(node.right, op_type)
            return [node]

        def _build_binop(self, operands, op_type):
            current = operands[0]
            for operand in operands[1:]:
                current = ast.BinOp(left=current, op=op_type(), right=operand)
            return current

    new_tree = CanonicalTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree)


class SyntaxValidator:
    COMMUTATIVE_BINOPS = (ast.Add, ast.Mult)
    COMMUTATIVE_FUNCTIONS = {"add", "multiply", "min", "max", "equal", "not_equal"}

    @staticmethod
    def operator_accepts_arity(operator_name: str, arg_count: int) -> bool:
        min_args, max_args = config.OPERATOR_ARITY.get(operator_name, (0, None))
        if arg_count < min_args:
            return False
        if max_args is not None and arg_count > max_args:
            return False
        return True

    @staticmethod
    def _has_operator_call(tree) -> bool:
        """True if the parsed expression contains at least one FastExpr operator
        call. Used to reject structurally trivial expressions -- a bare field or
        constant such as 'low', '10' or '20' -- that are technically parseable
        but are not real alphas. These can be produced when crossover grafts a
        leaf node into the root slot, collapsing a whole alpha down to a single
        field/number; simulating them just wastes submissions."""
        return any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            for node in ast.walk(tree)
        )

    @staticmethod
    @lru_cache(maxsize=8192)
    def structural_motifs(expression: str, min_depth: int = 2) -> frozenset:
        """Return the set of canonical structural MOTIFS in an expression.

        Each motif is the unparse of a function-call subtree (depth >= min_depth)
        with concrete fields abstracted to their data-GROUP and integer constants
        collapsed to a generic token, so e.g. ts_zscore(ts_delta(close, 5), 20)
        and ts_zscore(ts_delta(open, 10), 60) share the motif
        ts_zscore(ts_delta(<price>, <n>), <n>). Used for Frequent Subtree
        Avoidance, AST de-duplication and originality scoring.
        """
        try:
            tree = _parse_expression(expression)
        except Exception:
            return frozenset()

        field_to_group = _get_field_to_group()
        class _Abstract(ast.NodeTransformer):
            def visit_Name(self, node):
                grp = field_to_group.get(node.id)
                new_id = f"<{grp}>" if grp else node.id
                return ast.copy_location(ast.Name(id=new_id, ctx=ast.Load()), node)

            def visit_Constant(self, node):
                if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    return ast.copy_location(ast.Constant(value="<n>"), node)
                return node

        def _depth(node):
            return 1 + max((_depth(c) for c in ast.iter_child_nodes(node)), default=0)

        motifs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if _depth(node) < min_depth:
                    continue
                try:
                    abstracted = _Abstract().visit(copy.deepcopy(node))
                    ast.fix_missing_locations(abstracted)
                    motifs.add(ast.unparse(abstracted))
                except Exception:
                    continue
        return frozenset(motifs)

    @staticmethod
    def motif_similarity(expression: str, reference_expressions) -> float:
        """Max AST-motif Jaccard similarity of expression vs each reference."""
        a = SyntaxValidator.structural_motifs(expression)
        if not a or not reference_expressions:
            return 0.0
        best = 0.0
        for ref in reference_expressions:
            b = SyntaxValidator.structural_motifs(ref)
            if not b:
                continue
            union = len(a | b)
            if union:
                best = max(best, len(a & b) / union)
        return best

    @staticmethod
    def canonicalize(expression: str) -> str:
        return _canonicalize_cached(expression)

    @staticmethod
    def is_tautology(expression: str) -> bool:
        # Detect genuinely degenerate sub-expressions: x / x (== 1) and x - x
        # (== 0). On a parse error we return False (NOT True): a string that
        # already passed validation should not be discarded as a tautology just
        # because canonicalization hiccuped.
        try:
            tree = _parse_expression(expression)
        except Exception:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and type(node.op) in (ast.Div, ast.Sub):
                try:
                    left = SyntaxValidator.canonicalize(ast.unparse(node.left))
                    right = SyntaxValidator.canonicalize(ast.unparse(node.right))
                except Exception:
                    continue
                if left == right:
                    return True
        return False

    @staticmethod
    def violates_hard_affinity(tree) -> bool:
        """True when the expression contains a HARD-forbidden operator/field
        combination. Currently one rule: a first-difference / change operator
        (config.DELTA_LIKE_OPERATORS) applied anywhere over a ROLLING-TENOR field
        (config.ROLLING_TENOR_STEMS). On such fields the tenor label itself rolls
        forward every period, so a delta measures the roll -- a fake jump -- not a
        real change in the underlying. Deliberately NARROW: ts_delta stays valid
        on genuine step/event fields, and everything else is governed by the SOFT
        affinity weighting in the engine, not forbidden here. Disabled via
        config.AFFINITY_HARD_GUARD_ENABLED."""
        if not getattr(config, "AFFINITY_HARD_GUARD_ENABLED", False):
            return False
        delta_ops = {o.lower() for o in getattr(config, "DELTA_LIKE_OPERATORS", [])}
        stems = [s.lower() for s in getattr(config, "ROLLING_TENOR_STEMS", [])]
        if not delta_ops or not stems:
            return False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id.lower() in delta_ops):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Name) and any(s in inner.id.lower() for s in stems):
                        return True
        return False

    @staticmethod
    def parse_and_validate(expression: str):
        try:
            expression = SyntaxValidator._rectify_syntax(expression)
            tree = _parse_expression(expression)
            validator = AlphaSyntaxValidator()
            validator.visit(tree)
            # Reject structurally trivial "alphas": a bare field (Name) or
            # constant, or any expression with no operator call at all (e.g.
            # "10", "20", "low"). Every real alpha in this system is an operator
            # expression, so a leaf-only result is always degenerate.
            if not SyntaxValidator._has_operator_call(tree):
                raise ValueError("Trivial expression: no operator call")
            # Hard affinity guard: block the small set of genuinely meaningless
            # operator/field combos (e.g. a first-difference operator on a
            # rolling-tenor field). Soft preferences are handled in the engine;
            # only certainties are forbidden here.
            if SyntaxValidator.violates_hard_affinity(tree):
                raise ValueError("Hard affinity guard: forbidden operator/field combination")
            return True, SyntaxValidator.canonicalize(expression)
        except (ValueError, SyntaxError, TypeError) as e:
            logger.debug(f"Syntax validation failed for '{expression}': {e}")
            return False, expression

    @staticmethod
    def _rectify_syntax(expression: str) -> str:
        # IMPORTANT: we deliberately do NOT try to repair malformed expressions
        # by inserting commas (the old `(\w+)\s+(\d+)` -> `\1, \2` heuristic could
        # silently corrupt otherwise-valid formulas). We only normalize
        # whitespace and smart quotes; anything still malformed is REJECTED by
        # parse_and_validate rather than rewritten.
        left_smart = chr(0x201C)
        right_smart = chr(0x201D)
        expression = expression.replace(left_smart, "'").replace(right_smart, "'")
        expression = re.sub(r"\s+", " ", expression)
        return expression.strip()