import ast
import asyncio
import copy
import hashlib
import json
import logging
import math
import os
import random
import time
from urllib.parse import urlparse
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine, AuthenticationError
from oos_deflation import OOSDeflationEngine
from llm_seed_generator import LLMSeedGenerator
from syntax_validator import SyntaxValidator
from forge2_checks import parse_checks
from forge2_experiments import IndeterminateAttemptError
from forge2_storage import atomic_json, as_tuples
from forge2_expression import semantic_mutation, projection_mutation, typed_crossover, type_errors

logger = logging.getLogger(__name__)

# Expression node types that are valid crossover/mutation targets.
EXPR_NODES = (ast.Call, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Compare)

_SHORT_LOOKBACKS = [5, 10, 15, 20, 22]
_LONG_LOOKBACKS = [60, 120, 180, 252]

# --- Per-template decay priors (Upgrade C) ---------------------------------
# Different data families decay at different speeds, so seeding every alpha with
# a uniformly random decay wastes simulations. These stems map an expression to
# a suggested decay PRIOR (snapped to the nearest configured DECAY); the prior
# is applied only probabilistically so the refiner still explores the full grid.
_FAST_DECAY_STEMS = tuple(getattr(config, "DECAY_FAST_STEMS",
                     ("atmiv", "exerniv", "_iv", "clshv", "orhv", "straddle",
                      "strap", "ernmv", "impernmv", "slope", "ern4_")))
_SLOW_DECAY_STEMS = tuple(getattr(config, "DECAY_SLOW_STEMS",
                     ("guidance", "estimate", "consensus", "eps", "ebitda",
                      "sales", "netprofit", "cfo", "fcf", "capex", "bookvalue",
                      "fundamental")))
_MID_DECAY_STEMS = tuple(getattr(config, "DECAY_MID_STEMS",
                    ("sentiment", "snt1", "snt_", "news", "social", "buzz",
                     "mood", "focusrank", "stockrank", "torpedo")))


def _suggest_decay(expression):
    """Suggest a decay for a seed expression from its data-family stems:
    fast options/vol -> ~0, slow analyst/fundamental -> ~15, sentiment -> ~5.
    Returns a value snapped to the nearest configured DECAY, or None when no
    family matches (caller then falls back to a random decay)."""
    e = (expression or "").lower()
    if any(s in e for s in _FAST_DECAY_STEMS):
        target = 0
    elif any(s in e for s in _SLOW_DECAY_STEMS):
        target = 15
    elif any(s in e for s in _MID_DECAY_STEMS):
        target = 5
    else:
        return None
    if not config.DECAYS:
        return None
    return min(config.DECAYS, key=lambda d: abs(d - target))


def _ast_depth(expression: str) -> int:
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        return 1

    def depth(node):
        children = list(ast.iter_child_nodes(node))
        return 1 + max((depth(c) for c in children), default=0)

    return depth(tree)


def _alpha_skeleton(expression):
    """Structural signature of an alpha with field names, constants and the
    neutralization group collapsed to '_': the nested shape of operator calls
    only. group_neutralize(rank(close), INDUSTRY) and group_neutralize(rank(
    sales), SECTOR) share the skeleton 'group_neutralize(rank(_),_)'. Used to cap
    how much of the population any single template SHAPE may occupy so the search
    cannot collapse onto one skeleton (e.g. group_neutralize(rank(_)))."""
    try:
        tree = ast.parse(expression, mode="eval").body
    except Exception:
        return expression or "_"

    def sig(node):
        if isinstance(node, ast.Call):
            fname = node.func.id if isinstance(node.func, ast.Name) else "?"
            parts = [sig(a) for a in node.args] + [sig(k.value) for k in node.keywords]
            return fname + "(" + ",".join(parts) + ")"
        if isinstance(node, ast.UnaryOp):
            return "u(" + sig(node.operand) + ")"
        if isinstance(node, ast.BinOp):
            return "b(" + sig(node.left) + "," + sig(node.right) + ")"
        if isinstance(node, ast.Compare):
            return "cmp(" + sig(node.left) + ")"
        return "_"

    return sig(tree)


def _dominant_field(expression, field_set):
    """The data field a candidate most heavily relies on: the most common
    field-name token (restricted to `field_set`) in its AST, or None when it
    references no known field. Used by the selection-time field-diversity cap to
    stop one or two high-fitness fields from crowding the whole population (the
    observed implied-vol monoculture). Ties broken by first occurrence."""
    if not field_set:
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        return None
    counts = Counter(n.id for n in ast.walk(tree)
                     if isinstance(n, ast.Name) and n.id in field_set)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _split_group_neutralize(expression):
    """If the outermost call is group_neutralize(inner, GROUP), return
    (inner_expression_str, group_token_str); otherwise (None, None).

    Used to (a) re-wrap the inner logic during ts mutation instead of wrapping
    the whole neutralized alpha, and (b) vary the neutralization in grid search.
    """
    try:
        node = ast.parse(expression, mode="eval").body
    except Exception:
        return None, None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id.lower() == "group_neutralize" and len(node.args) == 2):
        group = node.args[1]
        if isinstance(group, ast.Name):
            try:
                return ast.unparse(node.args[0]), group.id
            except Exception:
                return None, None
    return None, None


def _negate_signal_str(signal_expr):
    """AST-negate a signal: fold -(-x) -> x (so we never stack '--'), otherwise
    wrap it in a unary minus. Returns the unparsed string, or None if it cannot
    be parsed."""
    try:
        node = ast.parse(signal_expr, mode="eval").body
    except Exception:
        return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        new_node = node.operand
    else:
        new_node = ast.UnaryOp(op=ast.USub(), operand=node)
    wrapped = ast.Expression(body=new_node)
    ast.fix_missing_locations(wrapped)
    try:
        return ast.unparse(wrapped)
    except Exception:
        return None


def _negate_expression(expression):
    """Return the sign-flipped (\"mirror\") alpha for a negative-Sharpe candidate.
    group_neutralize is LINEAR, so negating the whole alpha == negating its inner
    signal; we negate the inner signal and keep neutralization outermost
    (group_neutralize(-signal, GROUP)) to match the engine's canonical shape.
    Returns the validated canonical form, or None when the result is invalid,
    tautological, or unchanged from the input."""
    inner, group = _split_group_neutralize(expression)
    if inner is not None and group is not None:
        neg_inner = _negate_signal_str(inner)
        if neg_inner is None:
            return None
        candidate = f"group_neutralize({neg_inner}, {group})"
    else:
        candidate = _negate_signal_str(expression)
        if candidate is None:
            return None
    ok, canonical = SyntaxValidator.parse_and_validate(candidate)
    if not ok or SyntaxValidator.is_tautology(canonical) or canonical == expression:
        return None
    return canonical


def _strip_turnover_gate(expression):
    """Inverse of the turnover-gate lever: remove a trade_when(...) / keep(...)
    throttle so the signal is free to trade every day, which RAISES turnover. The
    inner signal of trade_when(cond, signal, close) is its 2nd argument; for
    keep(signal, ...) it is the 1st. Neutralization is kept outermost. Returns the
    validated canonical form, or None when there is no gate to strip or the result
    is invalid/unchanged."""
    inner, group = _split_group_neutralize(expression)
    target = inner if inner is not None else expression
    try:
        node = ast.parse(target, mode="eval").body
    except Exception:
        return None
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return None
    name = node.func.id.lower()
    if name == "trade_when" and len(node.args) >= 2:
        signal_node = node.args[1]
    elif name == "keep" and len(node.args) >= 1:
        signal_node = node.args[0]
    else:
        return None
    try:
        signal_str = ast.unparse(signal_node)
    except Exception:
        return None
    candidate = f"group_neutralize({signal_str}, {group})" if group is not None else signal_str
    ok, canonical = SyntaxValidator.parse_and_validate(candidate)
    if not ok or SyntaxValidator.is_tautology(canonical) or canonical == expression:
        return None
    return canonical


def _swap_smoother_to_decay(expression):
    """Sharpe-preserving turnover lever: replace a flat ts_mean(x, w) smoother
    with ts_decay_linear(x, w) over the SAME window. A decay-linear weights recent
    days more, so the book moves a little more each day (higher turnover) while
    keeping the full lookback horizon -- so a just-below-1% alpha is lifted over
    the floor WITHOUT sliding down the turnover-Sharpe frontier (the empirically
    best fix for an over-smoothed low-turnover winner). Returns the validated
    canonical form, or None when there is no ts_mean to swap / the result is
    unchanged."""
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        return None
    swapped = {"done": False}

    class _Swap(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if (isinstance(node.func, ast.Name)
                    and node.func.id.lower() == "ts_mean" and len(node.args) == 2):
                swapped["done"] = True
                return ast.Call(
                    func=ast.Name(id="ts_decay_linear", ctx=ast.Load()),
                    args=node.args, keywords=[])
            return node

    new_tree = _Swap().visit(tree)
    if not swapped["done"]:
        return None
    ast.fix_missing_locations(new_tree)
    try:
        candidate = ast.unparse(new_tree)
    except Exception:
        return None
    ok, canonical = SyntaxValidator.parse_and_validate(candidate)
    if not ok or SyntaxValidator.is_tautology(canonical) or canonical == expression:
        return None
    return canonical


@dataclass
class SimulationResult:
    expression: str
    universe: str
    decay: int
    sharpe: float = -1.0
    turnover: float = 1.0
    returns: float = 0.0
    alpha_id: str = ""
    skew: float = 0.0
    kurtosis: float = 0.0  # EXCESS kurtosis (normal == 0); see config.KURTOSIS_IS_EXCESS
    drawdown: float | None = None  # IS max drawdown as a fraction (BRAIN 'is.drawdown')
    margin: float | None = None    # IS margin / $ traded (BRAIN 'is.margin'); can be < 0
    track_record_length: int = config.DEFAULT_TRACK_RECORD_LENGTH
    oos_sharpe: float | None = None
    # Comma-joined names of BRAIN is.checks that FAILED (concentration, sub-
    # universe Sharpe, turnover floor, ...). Empty == BRAIN-clean / no checks.
    failed_checks: str = "CHECKS_UNVERIFIABLE"
    sharpe_2y: float | None = None
    pnl_realization: float | None = None
    pyramid_multiplier: float | None = None
    valid: bool = False


class GeneticEngine:
    """AST-level mutation & crossover. Every output is validated; on any failure
    we fall back to a parent expression so the pipeline never sees garbage."""

    def __init__(self):
        self._field_set = set(config.DATA_DICTIONARY)
        self._field_group = {}
        for group, fields in config.FIELD_GROUPS.items():
            for f in fields:
                self._field_group[f] = group
        # Harvested COMPOUND fields (e.g. "vec_avg(ern4_erneffct11)",
        # "ts_backfill(anl4_..., 120)") enter the vocabulary as whole expression
        # strings, so their INNER bare field names are not in _field_set and the
        # field-swap / spread mutations (which match ast.Name) could never evolve
        # anything INSIDE them -- the harvested vector/sparse vocabulary would be
        # seeded but then frozen. Register each inner bare field Name (mapped to
        # the compound's own group) so mutation can reach inside compound fields.
        operator_names = set(getattr(config, "OPERATOR_CATEGORIES", {}) or {})
        for entry in list(self._field_set):
            if "(" not in entry:
                continue
            try:
                etree = ast.parse(entry, mode="eval")
            except Exception:
                continue
            entry_group = self._field_group.get(entry)
            for inner in {n.id for n in ast.walk(etree) if isinstance(n, ast.Name)}:
                if inner in operator_names:
                    continue  # skip the operator/function names, keep data fields
                self._field_set.add(inner)
                if entry_group and inner not in self._field_group:
                    self._field_group[inner] = entry_group
        allowed = set(config.ALLOWED_OPERATORS)
        preferred = ["ts_rank", "ts_zscore", "ts_mean", "ts_delta", "ts_std_dev", "ts_decay_linear", "ts_av_diff"]
        self._ts_wrap_ops = [o for o in preferred if o in allowed and SyntaxValidator.operator_accepts_arity(o, 2)]
        if not self._ts_wrap_ops:
            self._ts_wrap_ops = [o for o in preferred if o in allowed]
        self._mutation_ops = [self._mutate_lookback, self._mutate_field, self._mutate_operator, self._mutate_wrap_ts]
        # WorldQuant turnover levers (trade_when / keep). Only those present in
        # the live operator set are used; the turnover-gate mutation is appended
        # when at least one is available so the GA can actively throttle churn.
        self._turnover_gate_ops = [o for o in ("trade_when", "keep") if o in set(config.ALLOWED_OPERATORS)]
        if getattr(config, "TURNOVER_GATE_MUTATION_ENABLED", True) and self._turnover_gate_ops:
            self._mutation_ops.append(self._mutate_gate_turnover)
        # Spread/combination mutation (Upgrade D): combine two same-group fields
        # into a near-minus-far style spread. Enabled only when an additive op is
        # in the live set AND SPREAD_MUTATION_ENABLED; an empty _spread_ops
        # disables spreads everywhere (mutation + decorrelation refinement).
        # Malformed grafts are rejected by the validator inside mutate().
        self._spread_ops = ([o for o in ("subtract", "add") if o in allowed]
                            if getattr(config, "SPREAD_MUTATION_ENABLED", True) else [])
        if self._spread_ops:
            self._mutation_ops.append(self._mutate_spread)
        # Neutralization-style mutation (monoculture breaker): re-wrap a signal's
        # OUTER neutralization into a different style (normalize / zscore /
        # group_zscore / group_rank / vector_neut). Operator mutation alone can
        # never do this -- it only swaps WITHIN a category, and group_neutralize
        # is "Group" while the cross-sectional neutralizers are not. Only styles
        # present in the live operator set are offered, so an absent operator is
        # silently skipped instead of producing a guaranteed validator reject.
        allowed_lower = {o.lower() for o in allowed}
        self._neut_styles = [s for s in getattr(config, "NEUTRALIZATION_STYLES", [])
                             if s.lower() in allowed_lower]
        if (getattr(config, "NEUTRALIZATION_MUTATION_ENABLED", True)
                and len(self._neut_styles) > 1):
            self._mutation_ops.append(self._mutate_neutralization)
        if getattr(config, "VECTOR_PROJECTION_MUTATION_ENABLED", False):
            self._mutation_ops.append(self._mutate_vector_projection)
        # Over-used winner motifs to avoid (set by the factory each generation).
        self.avoid_motifs = set()

    def _mutate_vector_projection(self, expression):
        return projection_mutation(expression, config.ALLOWED_OPERATORS)

    # --- operator-field affinity helpers (SOFT economic prior) ---------------
    # These let the random mutators STEER toward economically-sensible operator/
    # field pairings (config.OPERATOR_AFFINITY) instead of pairing blindly. They
    # only re-weight sampling -- every operator/field stays reachable -- so the
    # engine remains fully general. All fall back to a uniform random.choice when
    # affinity is disabled, the family is unknown, or the option set is tiny.
    @staticmethod
    def _nearest_operator(tree, target):
        """Func name of the nearest enclosing operator Call above `target` (or
        None), so a field-swap knows which operation it is feeding."""
        parent = {}
        for p in ast.walk(tree):
            for c in ast.iter_child_nodes(p):
                parent[c] = p
        node = parent.get(target)
        while node is not None:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                return node.func.id
            node = parent.get(node)
        return None

    @staticmethod
    def _family_of_tree(root):
        """Most common affinity family among the field Names under `root`."""
        fams = Counter()
        for n in ast.walk(root):
            if isinstance(n, ast.Name):
                fam = config.field_family(n.id)
                if fam:
                    fams[fam] += 1
        return fams.most_common(1)[0][0] if fams else None

    def _dominant_family(self, expression):
        try:
            tree = ast.parse(expression, mode="eval")
        except Exception:
            return None
        return self._family_of_tree(tree)

    def _call_family(self, node):
        return self._family_of_tree(node)

    def _affinity_field_choice(self, pool, operator_name):
        """random.choice over `pool`, soft-weighted so fields whose family suits
        `operator_name` are favoured."""
        if (not getattr(config, "AFFINITY_ENABLED", False) or not operator_name
                or len(pool) < 2):
            return random.choice(pool)
        weights = [config.operator_affinity_weight(operator_name, config.field_family(f))
                   for f in pool]
        if sum(weights) <= 0:
            return random.choice(pool)
        return random.choices(pool, weights=weights, k=1)[0]

    def _affinity_op_choice(self, ops, family):
        """random.choice over operator names `ops`, soft-weighted toward those
        suited to `family`."""
        if not getattr(config, "AFFINITY_ENABLED", False) or not family or len(ops) < 2:
            return random.choice(ops)
        weights = [config.operator_affinity_weight(o, family) for o in ops]
        if sum(weights) <= 0:
            return random.choice(ops)
        return random.choices(ops, weights=weights, k=1)[0]

    # --- mutation primitives -------------------------------------------------
    def _mutate_lookback(self, expression):
        tree = ast.parse(expression, mode="eval")
        consts = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
        if not consts:
            return None
        node = random.choice(consts)
        node.value = random.choice(_SHORT_LOOKBACKS + _LONG_LOOKBACKS)
        return ast.unparse(tree)

    def _mutate_field(self, expression):
        if getattr(config, "SEMANTIC_MUTATION_ENABLED", False):
            metadata = {k:v for k,v in config.FIELD_METADATA.items()
                        if k in config.SEMANTIC_ACTIVE_FIELDS}
            return semantic_mutation(expression, metadata)
        tree = ast.parse(expression, mode="eval")
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in self._field_set]
        if not names:
            return None
        node = random.choice(names)
        group = self._field_group.get(node.id)
        pool = config.FIELD_GROUPS[group] if group else config.DATA_DICTIONARY
        # Soft affinity: bias the replacement toward fields whose data family
        # economically SUITS the operator that wraps this slot (e.g. keep a
        # first-difference ts_delta over change-like fields, a ranking op over
        # level-like ones). Re-weights sampling only -- the whole group is still
        # reachable -- so the search stays general.
        operator_name = self._nearest_operator(tree, node)
        node.id = self._affinity_field_choice(pool, operator_name)
        return ast.unparse(tree)

    def _mutate_operator(self, expression):
        tree = ast.parse(expression, mode="eval")
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        if not calls:
            return None
        node = random.choice(calls)
        name = node.func.id.lower()
        arg_count = len(node.args) + len(node.keywords)
        category = config.OPERATOR_CATEGORIES.get(name)
        alternatives = [o for o in config.OPERATORS_BY_CATEGORY.get(category, [])
                        if o != name and SyntaxValidator.operator_accepts_arity(o, arg_count)]
        if not alternatives:
            return None
        # Soft affinity: prefer a replacement operator suited to the family of
        # the fields this call acts on (weights only; any in-category, arity-
        # valid operator is still reachable).
        node.func.id = self._affinity_op_choice(alternatives, self._call_family(node))
        return ast.unparse(tree)

    def _mutate_wrap_ts(self, expression):
        if not self._ts_wrap_ops:
            return None
        # Soft affinity: pick the wrapping ts operator suited to the expression's
        # dominant data family (e.g. don't wrap a rolling-tenor IV chain in a
        # first-difference op). Weights only -- all ts ops stay reachable.
        op = self._affinity_op_choice(self._ts_wrap_ops, self._dominant_family(expression))
        window = random.choice(_SHORT_LOOKBACKS + _LONG_LOOKBACKS)
        # Wrap the INNER logic and keep neutralization outermost, rather than
        # producing ts_rank(group_neutralize(...), w) which neutralizes-then-
        # ranks (conceptually backwards).
        inner, group = _split_group_neutralize(expression)
        if inner is not None and group is not None:
            return f"group_neutralize({op}({inner}, {window}), {group})"
        return f"{op}({expression}, {window})"

    def _mutate_gate_turnover(self, expression):
        """Throttle rebalancing with a WorldQuant turnover lever. trade_when only
        re-trades while a (slow) regime condition holds and otherwise holds the
        prior book (third arg -1 = never force-close); keep damps churn by holding
        the signal. Neutralization stays outermost. Returns None when no turnover
        operator exists in the live set; any malformed result is rejected by the
        validator inside mutate()."""
        if not self._turnover_gate_ops:
            return None
        inner, group = _split_group_neutralize(expression)
        signal = inner if inner is not None else expression
        op = random.choice(self._turnover_gate_ops)
        window = random.choice(_LONG_LOOKBACKS)
        if op == "keep":
            gated = f"keep({signal}, 0, {window})"
        else:
            gate_field = random.choice(config.DATA_DICTIONARY)
            gated = f"trade_when(ts_zscore({gate_field}, {window}) > 0, {signal}, -1)"
        if group is not None:
            return f"group_neutralize({gated}, {group})"
        return gated

    def _mutate_spread(self, expression):
        """Upgrade D: replace one field with a spread of two SAME-GROUP fields
        (proxy for same-dataset term structure), e.g. field -> subtract(field,
        sibling). Builds a novel relative signal; the validator rejects any
        type/arity-invalid result inside mutate()."""
        if not getattr(self, "_spread_ops", None):
            return None
        tree = ast.parse(expression, mode="eval")
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in self._field_set]
        if not names:
            return None
        node = random.choice(names)
        group = self._field_group.get(node.id)
        pool = [f for f in (config.FIELD_GROUPS.get(group) or config.DATA_DICTIONARY) if f != node.id]
        if not pool:
            return None
        sibling = random.choice(pool)
        op = random.choice(self._spread_ops)
        try:
            repl = ast.parse(f"{op}({node.id}, {sibling})", mode="eval").body
        except Exception:
            return None
        replaced = {"done": False}

        class _Swap(ast.NodeTransformer):
            def visit_Name(self, n):
                if n is node and not replaced["done"]:
                    replaced["done"] = True
                    return repl
                return n

        new_tree = _Swap().visit(tree)
        ast.fix_missing_locations(new_tree)
        try:
            return ast.unparse(new_tree)
        except Exception:
            return None

    def _mutate_neutralization(self, expression):
        """Monoculture breaker: re-wrap the OUTER neutralization of a
        group_neutralize(signal, GROUP) alpha into a DIFFERENT neutralization
        style, so the search escapes the single-neutralizer (always
        group_neutralize) collapse. Styles:
          * normalize / zscore       -> market-wide neutralizers (drop the GROUP);
          * group_zscore / group_rank -> keep the GROUP, change the within-group op;
          * vector_neut(signal, rank(risk)) -> ORTHOGONALIZE the signal against a
            ranked risk field, the published WorldQuant lever for decorrelating
            an over-collinear family (e.g. orthogonalize an IV-heavy alpha
            against a base risk field). The risk field is drawn from the LIVE
            DATA_DICTIONARY but EXCLUDES the fields the signal already uses, so
            vector_neut can't (partly) cancel the very signal we want to keep.
        Only fires on a group_neutralize-rooted alpha; returns None otherwise so
        mutate() simply retries another operator. The validator inside mutate()
        rejects any malformed result."""
        styles = getattr(self, "_neut_styles", None)
        if not styles:
            return None
        inner, group = _split_group_neutralize(expression)
        if inner is None or group is None:
            return None
        choices = [s for s in styles if s.lower() != "group_neutralize"]
        if not choices:
            return None
        style = random.choice(choices)
        s = style.lower()
        if s == "vector_neut":
            pool = config.DATA_DICTIONARY
            if not pool:
                return None
            # vector_neut(x, y) projects x off y, so the risk vector y must NOT
            # be one of the signal's own fields -- orthogonalizing against itself
            # would cancel the very signal we want to keep. Draw y from OUTSIDE
            # the inner expression's fields (fall back to the full pool only if
            # the signal somehow uses every field).
            try:
                used = {n.id for n in ast.walk(ast.parse(inner, mode="eval"))
                        if isinstance(n, ast.Name)}
            except Exception:
                used = set()
            risk_pool = [f for f in pool if f not in used] or pool
            risk = random.choice(risk_pool)
            candidate = f"vector_neut({inner}, rank({risk}))"
        elif s in ("group_zscore", "group_rank"):
            candidate = f"{style}({inner}, {group})"
        else:  # normalize / zscore / any other 1-arg cross-sectional neutralizer
            candidate = f"{style}({inner})"
        return candidate

    def mutate(self, expression):
        for _ in range(4):
            op = random.choice(self._mutation_ops)
            try:
                candidate = op(expression)
            except Exception:
                candidate = None
            if candidate and candidate != expression:
                ok, canonical = SyntaxValidator.parse_and_validate(candidate)
                if (ok and not SyntaxValidator.is_tautology(canonical)
                        and (not getattr(config,"SEMANTIC_MUTATION_ENABLED",False)
                             or not type_errors(canonical,config.FIELD_METADATA))):
                    # Frequent Subtree Avoidance (Upgrade #3): don't lock onto an
                    # over-used winner motif -- reject (and retry) with
                    # probability (1 - FSA_PENALTY) so mutation keeps exploring.
                    if (self.avoid_motifs and config.FSA_ENABLED
                            and SyntaxValidator.structural_motifs(canonical) & self.avoid_motifs
                            and random.random() > config.FSA_PENALTY):
                        continue
                    return canonical
        return expression

    # --- crossover -----------------------------------------------------------
    @staticmethod
    def _expression_slots(tree):
        slots = []
        for parent in ast.walk(tree):
            for field_name, value in ast.iter_fields(parent):
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, EXPR_NODES):
                            slots.append((parent, field_name, i, item))
                elif isinstance(value, EXPR_NODES):
                    slots.append((parent, field_name, None, value))
        return slots

    def crossover(self, expr1, expr2):
        if getattr(config,"SEMANTIC_MUTATION_ENABLED",False):
            child=typed_crossover(expr1,expr2,config.FIELD_METADATA)
            if child:
                ok,canonical=SyntaxValidator.parse_and_validate(child)
                if ok and not SyntaxValidator.is_tautology(canonical):return canonical
            return expr1
        try:
            base = ast.parse(expr1, mode="eval")
            t2 = ast.parse(expr2, mode="eval")
        except Exception:
            return expr1
        donors = [n for n in ast.walk(t2) if isinstance(n, EXPR_NODES)]
        # Prefer grafting non-trivial subtrees (operator calls / compound nodes)
        # so crossover can't collapse an alpha down to a bare field or constant
        # (e.g. "low", "10") when a leaf donor lands in the root slot. Bare
        # leaves are only used as a last resort.
        rich_donors = [n for n in donors
                       if isinstance(n, (ast.Call, ast.BinOp, ast.UnaryOp, ast.Compare))]
        donor_pool = rich_donors or donors
        if not donor_pool:
            return expr1
        # Retry a few times on a FRESH copy each round: a single bad graft (or a
        # trivial/tautological result rejected by the validator) should not waste
        # the whole crossover and fall straight back to a parent.
        for _ in range(4):
            t1 = copy.deepcopy(base)
            slots = self._expression_slots(t1)
            if not slots:
                break
            parent, field_name, index, _ = random.choice(slots)
            donor = copy.deepcopy(random.choice(donor_pool))
            if index is None:
                setattr(parent, field_name, donor)
            else:
                getattr(parent, field_name)[index] = donor
            ast.fix_missing_locations(t1)
            try:
                candidate = ast.unparse(t1)
            except Exception:
                continue
            ok, canonical = SyntaxValidator.parse_and_validate(candidate)
            if ok and not SyntaxValidator.is_tautology(canonical) and canonical != expr1:
                return canonical
        return expr1


class AlphaFactory:
    def __init__(self):
        if config.RANDOM_SEED is not None:
            random.seed(config.RANDOM_SEED)
            np.random.seed(config.RANDOM_SEED)
        self.db = DatabaseManager()
        self.network = NetworkEngine()
        self.deflation = OOSDeflationEngine()
        self.llm = LLMSeedGenerator()
        self.genetic = GeneticEngine()

        self.population = []
        self.basket_report={"reason":"not_evaluated"}
        self.result_cache = {}
        self._proposal_lineage = {}
        # alpha_id -> {date: cumulative_pnl} cache for the return-orthogonality
        # selection lever. Populated on simulate + lazily from the alpha_pnl
        # table on resume; trimmed in _trim_state (elite PnL is always
        # reloadable from the DB, so dropping old entries is safe).
        self._pnl_by_alpha_id = {}
        self.history_scores = []
        self.loser_exprs = []
        # Expressions of alphas that cleared the promotion gates -- the basis for
        # success-side Frequent Subtree Avoidance (Upgrade #3).
        self.winner_exprs = []
        # Top-K over-used winner motifs to steer seeding/mutation away from.
        self._avoid_motifs = set()
        # Structured recent-failure memory ({expression, reason}) fed back into
        # seed generation so the grammar engine and optional LLM steer away from
        # known-bad structures/fields. See llm_seed_generator.ExperienceMemory.
        self.experience = []
        self.evaluated_canon = set()
        self.refined = set()
        self.submission_count = 0
        self.generation = 0
        # Mid-generation resume state. Populated by _restore_checkpoint when a
        # run was interrupted AFTER this generation's offspring batch was
        # generated but BEFORE the generation finished evaluating. On resume the
        # loop replays exactly this batch (dedup skips the already-simulated
        # members) instead of regenerating a whole fresh generation.
        self._resume_generation = None
        self._resume_offspring = None
        self._resume_population_keys = None
        self._resume_population_snapshot = None
        self._recover_pending_keys = set()

        self.sim_semaphore = None
        self._state_lock = asyncio.Lock()
        self._active_tasks = set()

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _safe_float(value, default):
        if isinstance(value,bool):return default
        try:
            f = float(value)
            return f if math.isfinite(f) else default
        except (TypeError, ValueError):
            return default

    def _seed_decay(self, expression):
        """Per-template decay PRIOR (Upgrade C): bias a seed toward the decay that
        suits its data family (fast options/vol -> low, analyst/fundamental ->
        high, sentiment -> mid), while still exploring the full grid. The prior
        is applied only with probability SEED_DECAY_PRIOR_STRENGTH so the refiner
        can still discover a better decay; otherwise fall back to a uniform
        random decay."""
        prior = _suggest_decay(expression)
        strength = getattr(config, "SEED_DECAY_PRIOR_STRENGTH", 0.7)
        if prior is not None and random.random() < strength:
            return prior
        return random.choice(config.DECAYS)

    def _estimate_var_trials(self) -> float:
        sqrt_periods = math.sqrt(config.PERIODS_IN_YEAR)
        per_period = [s / sqrt_periods for s in self.history_scores if s is not None and math.isfinite(s)]
        if len(per_period) >= 2:
            return float(np.var(per_period))
        return (0.4 / sqrt_periods) ** 2

    def _shape_multiplier(self, sharpe, oos_sharpe, expression):
        """Multiplicative fitness penalty in (0, 1]: over-fitting risk (IS-OOS
        gap, Upgrade #6) x originality vs the crowded-alpha zoo (Upgrade #4)."""
        mult = self.deflation.overfitting_risk_multiplier(sharpe, oos_sharpe)
        if config.ORIGINALITY_ENABLED:
            sim = self.deflation.ast_similarity(expression, config.CROWDED_ALPHA_ZOO)
            if sim >= config.ORIGINALITY_PENALTY_SIMILARITY:
                mult *= config.ORIGINALITY_PENALTY
        return mult

    def _composite_fitness(self, adjusted_dsr, depth, sharpe, oos_sharpe, expression):
        """The ONE fitness definition used by BOTH live evaluation and resume:
        orthogonality-adjusted deflated Sharpe minus a parsimony term, scaled by
        the shape multiplier. The penalty is applied only to a positive base so
        it can never paradoxically improve an already-bad score. Centralizing it
        here keeps resumed and freshly-evaluated members directly comparable
        under NSGA-II selection."""
        fitness = adjusted_dsr - config.PARSIMONY_COEFFICIENT * depth
        if fitness > 0:
            fitness *= self._shape_multiplier(sharpe, oos_sharpe, expression)
        return fitness

    def _remember_failure(self, expression, reason):
        """Append a failed alpha + reason to the experience memory (capped), for
        failure-feedback steering during seeding."""
        if not config.EXPERIENCE_MEMORY_ENABLED or not expression:
            return
        self.experience.append({"expression": expression, "reason": reason})
        if len(self.experience) > config.EXPERIENCE_MEMORY_SIZE:
            self.experience = self.experience[-config.EXPERIENCE_MEMORY_SIZE:]

    def _refresh_avoid_motifs(self):
        """Recompute the top-K over-used motifs among winners for Frequent
        Subtree Avoidance, and publish them to the genetic engine (Upgrade #3)."""
        if not config.FSA_ENABLED or len(self.winner_exprs) < config.FSA_MIN_WINNERS:
            self._avoid_motifs = set()
            self.genetic.avoid_motifs = set()
            return
        counts = Counter()
        for expr in self.winner_exprs[-300:]:
            for motif in SyntaxValidator.structural_motifs(expr):
                counts[motif] += 1
        self._avoid_motifs = {m for m, _ in counts.most_common(config.FSA_TOP_K)}
        self.genetic.avoid_motifs = self._avoid_motifs

    def _log_pbo_diagnostic(self):
        """Log a single-split winner rank, explicitly not CSCV/PBO."""
        if not config.PBO_DIAGNOSTIC_ENABLED:
            return
        pairs = [(rec.get("sharpe"), rec.get("oos_sharpe")) for rec in self.population
                 if rec.get("oos_sharpe") is not None]
        if len(pairs) >= 4:
            pbo = self.deflation.single_split_winner_rank(pairs)
            logger.info(
                f"Single-split IS-winner OOS-rank diagnostic (not PBO) = {pbo:.2f} "
                f"over {len(pairs)} OOS-scored alphas."
            )

    def _trim_state(self):
        """Cap the unbounded run-state collections so a long (500-generation) run
        stays flat in memory. evaluated_canon is deliberately NOT trimmed -- it
        is the cross-generation dedup guard and must stay complete; precisely
        because of it, dropping old result_cache entries can never trigger a
        re-simulation (an evaluated key is filtered out before it ever reaches
        _simulate_alpha)."""
        hist_cap = max(config.POPULATION_SIZE * 5, 1000)
        if len(self.history_scores) > hist_cap:
            self.history_scores = self.history_scores[-hist_cap:]
        ref_cap = 1000  # only the last few hundred are ever read for dedup/FSA
        if len(self.loser_exprs) > ref_cap:
            self.loser_exprs = self.loser_exprs[-ref_cap:]
        if len(self.winner_exprs) > ref_cap:
            self.winner_exprs = self.winner_exprs[-ref_cap:]
        cache_cap = max(config.POPULATION_SIZE * 20, 5000)
        if len(self.result_cache) > cache_cap:
            # dict preserves insertion order -> keep the most recent entries.
            self.result_cache = dict(list(self.result_cache.items())[-cache_cap:])
        # Bound the PnL cache too. Elite PnL is always reloadable from the
        # alpha_pnl table (_elite_pnl_matrix falls back to the DB), so dropping
        # the oldest entries can never corrupt selection -- it only re-reads.
        pnl_cap = max(config.POPULATION_SIZE * 5, 2000)
        if len(self._pnl_by_alpha_id) > pnl_cap:
            self._pnl_by_alpha_id = dict(list(self._pnl_by_alpha_id.items())[-pnl_cap:])

    # --- lifecycle -----------------------------------------------------------
    async def initialize(self):
        if getattr(config,"RESEARCH_OFFLINE_ONLY",False) and not getattr(self.network,"offline_fixture",False):
            raise RuntimeError("Forge2 offline research mode: real transport initialization disabled")
        await self.db.init_db()
        self.sim_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SIMULATIONS)
        # Keep the session warm so idle gaps between simulations don't trigger a
        # premature logout during a long overnight run.
        await self.network.start_keepalive()
        history = await self.db.load_history()
        for row in history:
            expr, universe, decay, sharpe, turnover, skew, kurtosis, trl, alpha_id = row
            key = f"{expr}|{universe}|{decay}"
            self.evaluated_canon.add(key)
            self.result_cache[key] = SimulationResult(
                expression=expr, universe=universe, decay=decay,
                sharpe=sharpe if sharpe is not None else -1.0,
                turnover=turnover if turnover is not None else 1.0,
                skew=skew or 0.0, kurtosis=kurtosis if kurtosis is not None else 0.0,
                track_record_length=trl or config.DEFAULT_TRACK_RECORD_LENGTH,
                alpha_id=alpha_id or "", valid=sharpe is not None,
            )
            evidence_result = await self.db.load_evidence(alpha_id) if alpha_id else None
            if evidence_result:
                self.result_cache[key] = SimulationResult(**evidence_result)
            else:
                metrics = await self.db.load_checks(alpha_id) if alpha_id else {}
                checks = parse_checks(metrics)
                cached = self.result_cache[key]
                cached.failed_checks = ",".join(checks.failed) if checks.verified else "CHECKS_UNVERIFIABLE"
                cached.drawdown = self._safe_float(metrics.get("drawdown"),None)
                cached.margin = self._safe_float(metrics.get("margin"),None)
                cached.sharpe_2y = checks.sharpe_2y
                cached.pnl_realization = checks.pnl_realization
                cached.pyramid_multiplier = checks.pyramid_multiplier
                rows = await self.db.get_population_for_keys([[expr,universe,decay]])
                cached.returns = rows[0][12] or 0.0
                cached.oos_sharpe = rows[0][13]
            if sharpe is not None:
                self.history_scores.append(sharpe)
                if sharpe < config.MIN_SHARPE:
                    self.loser_exprs.append(expr)
        logger.info(f"Loaded {len(history)} historical alphas from memory.")
        self._restore_checkpoint()

    async def shutdown(self):
        for task in list(self._active_tasks):
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
            self._active_tasks.clear()
        await self.network.close()
        await self.db.close()

    # --- run-level checkpoint (survives forced logouts) ---------------------
    def _save_checkpoint(self, pending_offspring=None):
        """Persist run-level progress (next generation index + counters) so a
        restart after a logout resumes the cadence instead of replaying the loop
        from zero. The population itself is already checkpointed row-by-row in
        the database during evaluation.

        When pending_offspring is provided, this writes a MID-GENERATION
        checkpoint: it records the current generation's full offspring candidate
        list (expression|universe|decay) so an interrupted run resumes by
        finishing exactly that batch -- the result_cache/evaluated_canon dedup
        skips every offspring already simulated, so only the UNFINISHED ones are
        re-run instead of regenerating (and re-simulating) a whole fresh
        generation. The end-of-generation _save_checkpoint() call omits the
        pending block, which clears it once the generation completes."""
        try:
            data = {
                "checkpoint_type": "runtime_checkpoint",
                "generation": self.generation + 1,
                "submission_count": self.submission_count,
                "timestamp": time.time(),
                "random_state":random.getstate(),
                "population": [[r["expression"],r["universe"],r["decay"]] for r in self.population],
                "population_snapshot": [{**r,"distance": "infinity" if r.get("distance")==float("inf") else r.get("distance",0)} for r in self.population],
                "decision_state": {"history_scores":getattr(self,"history_scores",[]),"loser_exprs":getattr(self,"loser_exprs",[]),
                    "winner_exprs":getattr(self,"winner_exprs",[]),"experience":getattr(self,"experience",[]),
                    "refined":sorted(getattr(self,"refined",set())),"avoid_motifs":sorted(getattr(self,"_avoid_motifs",set()))},
                "epoch_id":os.getenv("FORGE2_EPOCH_ID"),
                "basket_report":getattr(self,"basket_report",{}),
            }
            if getattr(self, "warmstart_manifest", None) is not None:
                data["warmstart_manifest"] = self.warmstart_manifest
            if getattr(self, "warmstart_file_hash", None) is not None:
                data["warmstart_file_hash"] = self.warmstart_file_hash
            if getattr(self, "warmstart_provenance", None) is not None:
                data["warmstart_provenance"] = self.warmstart_provenance
            if pending_offspring is not None:
                # Still INSIDE this generation (not past it): resume must
                # re-enter self.generation, not the next one.
                data["generation"] = self.generation
                data["pending_generation"] = self.generation
                data["pending_offspring"] = [
                    {"expression": c["expression"], "universe": c["universe"],
                     "decay": c["decay"], "parent_id": c.get("parent_id"),
                     "mutation_type": c.get("mutation_type"), "origin": c.get("origin")}
                    for c in pending_offspring if c.get("expression")
                ]
            atomic_json(config.CHECKPOINT_PATH,data)
        except Exception as e:
            logger.error(f"Could not write checkpoint: {e}")
            raise RuntimeError("Checkpoint could not be committed; refusing to continue") from e

    def _restore_checkpoint(self):
        path = Path(config.CHECKPOINT_PATH)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("Checkpoint is corrupt; restore it rather than silently restarting") from exc
        if not isinstance(data, dict):
            raise ValueError("Invalid checkpoint data: expected JSON object")

        if data.get("schema_version") == "forge2-warmstart-v1" and data.get("checkpoint_type") == "runtime_checkpoint":
            raise ValueError("Invalid checkpoint: conflicting warmstart artifact schema and runtime checkpoint markers")

        expected_epoch = os.getenv("FORGE2_EPOCH_ID")
        if data.get("pending_offspring") and data.get("epoch_id") and expected_epoch != data["epoch_id"]:
            raise ValueError("Pending checkpoint belongs to a different vocabulary epoch")

        is_runtime_checkpoint = (
            data.get("checkpoint_type") == "runtime_checkpoint"
            or "population_snapshot" in data
            or "decision_state" in data
            or "pending_offspring" in data
            or (int(data.get("generation", 0)) > 0 and data.get("schema_version") != "forge2-warmstart-v1")
        )
        # Explicit artifact schemas outrank presence-only legacy heuristics.
        if data.get("schema_version") == "forge2-warmstart-v1":
            is_runtime_checkpoint = False

        is_warmstart_artifact = (
            not is_runtime_checkpoint
            and ("warmstart_manifest" in data or data.get("schema_version") == "forge2-warmstart-v1")
        )

        if is_warmstart_artifact:
            from forge2_warmstart import validate_warmstart_import
            receipt_path = path.with_name(f"{path.name}.receipt.json")
            receipt_data = None
            if receipt_path.is_file():
                try:
                    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            validation = validate_warmstart_import(
                data,
                checkpoint_path=path,
                expected_receipt=receipt_data,
                expected_epoch_id=expected_epoch,
            )
            self.warmstart_manifest = validation["manifest"]
            self.warmstart_file_hash = validation["file_hash"]
            self.warmstart_provenance = validation["provenance"]
            self.checkpoint_file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        elif is_runtime_checkpoint:
            self.checkpoint_file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if "warmstart_manifest" in data:
                self.warmstart_manifest = data["warmstart_manifest"]
            if "warmstart_file_hash" in data:
                self.warmstart_file_hash = data["warmstart_file_hash"]
            if "warmstart_provenance" in data:
                self.warmstart_provenance = data["warmstart_provenance"]
        else:
            self.checkpoint_file_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        decision = data.get("decision_state")
        if decision:
            for name in ("history_scores", "loser_exprs", "winner_exprs", "experience"):
                setattr(self, name, decision[name])
            self.refined = set(decision["refined"])
            self._avoid_motifs = set(decision["avoid_motifs"])
            if hasattr(self, "genetic") and self.genetic is not None:
                self.genetic.avoid_motifs = self._avoid_motifs.copy()
        self.basket_report = data.get("basket_report", {"reason": "legacy_checkpoint"})
        self._resume_population_snapshot = data.get("population_snapshot")
        if self._resume_population_snapshot is not None:
            for rec in self._resume_population_snapshot:
                if rec.get("distance") == "infinity":
                    rec["distance"] = float("inf")
        self.generation = int(data.get("generation", 0))
        self.submission_count = int(data.get("submission_count", 0))
        if data.get("random_state"):
            random.setstate(as_tuples(data["random_state"]))
        population = data.get("population")
        if population is not None:
            if not isinstance(population, list) or any(not isinstance(k, list) or len(k) != 3 for k in population):
                raise ValueError("Invalid checkpoint population")
            self._resume_population_keys = population
        # Mid-generation resume: if the interrupted run had already generated
        # this generation's offspring batch, reload it so run() finishes exactly
        # that batch (dedup skips the already-simulated members) instead of
        # redoing the whole generation. Absent/empty -> normal
        # generation-boundary resume (fully backward compatible).
        pending_gen = data.get("pending_generation")
        pending = data.get("pending_offspring")
        if pending_gen is not None and pending:
            self._resume_generation = int(pending_gen)
            self._resume_offspring = [
                {"expression": c["expression"], "universe": c["universe"],
                 "decay": c["decay"], "parent_id": c.get("parent_id"),
                 "mutation_type": c.get("mutation_type"), "origin": c.get("origin")}
                for c in pending
                if isinstance(c, dict) and c.get("expression")
            ]
            logger.info(
                f"Restored checkpoint: resuming at generation {self.generation} "
                f"({self.submission_count} prior submissions; finishing "
                f"{len(self._resume_offspring)} pending offspring from an "
                f"interrupted generation).")
        else:
            logger.info(
                f"Restored checkpoint: resuming at generation {self.generation} "
                f"({self.submission_count} prior submissions).")

    # --- simulation ----------------------------------------------------------
    async def _simulate_alpha(self, expression, universe, decay) -> SimulationResult:
        cache_key = f"{expression}|{universe}|{decay}"
        if cache_key in self.result_cache:
            return self.result_cache[cache_key]

        result = SimulationResult(expression=expression, universe=universe, decay=decay)
        payload = config.build_simulation_payload(expression, universe, decay)
        ledger=getattr(self,"experiment_ledger",None)
        attempt=ledger.prepare(payload,self.experiment_context,{**getattr(self,"_proposal_lineage",{}).get(cache_key,{}),"scoring_policy_hash":getattr(self,"scoring_policy_hash",None)}) if ledger else None
        if attempt and attempt["state"] in ("accepted","remote_complete","completed","expired_unresolved") and getattr(self,"trial_ledger",None):
            # Reconcile the separate shared counter from durable acceptance
            # evidence. A crash after receipt commit must not lower observed N.
            self.trial_ledger.record(self.trial_context,expression,universe,decay,payload=payload)
        if attempt and attempt["state"] in ("dispatching","expired_unresolved"):
            raise IndeterminateAttemptError("Remote acceptance unknown for attempt "+attempt["attempt_id"]+"; reconcile a recorded receipt, never automatically repost")
        if attempt and attempt["state"]=="failed":return result
        if attempt and attempt["state"]=="completed":
            saved=json.loads(attempt["result"]);result=SimulationResult(**saved["result"])
            await self._persist_raw_result(result,payload,saved["metrics"])
            self.result_cache[cache_key]=result
            return result

        # Hold a concurrency slot for the ENTIRE active lifetime of the
        # simulation -- the submission POST *and* the polling loop -- so the
        # number of simulations actually RUNNING on WorldQuant at once can never
        # exceed MAX_CONCURRENT_SIMULATIONS. Releasing the slot right after the
        # POST (the previous behaviour) only serialized the short POSTs while
        # letting an unbounded number of accepted simulations poll concurrently,
        # which is what kept the /simulations endpoint tripping sustained 429s.
        # The cheap, post-completion detail/correlation GETs run OUTSIDE the slot
        # so a finished simulation frees capacity immediately.
        alpha_id = None
        errored = False
        async with self.sim_semaphore:
            receipt=json.loads(attempt["receipt"]) if attempt and attempt.get("receipt") else {}
            if attempt and attempt["state"]=="remote_complete":
                alpha_id=receipt["alpha_id"]
                poll_url=None
            elif attempt and attempt["state"]=="accepted":
                poll_url=receipt["poll_url"]
            else:
                if ledger:ledger.dispatch(attempt["attempt_id"],getattr(config,"MAX_DISPATCHES",0))
                try:
                    resp = await self.network.request("POST", "/simulations", json=payload)
                except BaseException as exc:
                    if ledger and not isinstance(exc,asyncio.CancelledError):
                        raise IndeterminateAttemptError("Dispatch interrupted without receipt; no blind retry: "+attempt["attempt_id"]) from exc
                    raise
                self.submission_count += 1
                if resp["status_code"] not in (200, 201):
                    if ledger:
                        if resp["status_code"]>=500:raise IndeterminateAttemptError("Ambiguous simulation server error; attempt "+attempt["attempt_id"])
                        ledger.reject(attempt["attempt_id"],"HTTP "+str(resp["status_code"]))
                    self.result_cache[cache_key] = result
                    return result
                poll_url = resp.get("location")
                body = resp.get("json")
                if not poll_url and isinstance(body, dict):poll_url = body.get("location") or body.get("url")
                if not poll_url:
                    if ledger:raise IndeterminateAttemptError("Accepted simulation has no receipt; attempt "+attempt["attempt_id"])
                    return result
                if ledger:ledger.accept(attempt["attempt_id"],poll_url,time.time()+config.SIMULATION_POLL_TIMEOUT_SECS)
                if getattr(self,"trial_ledger",None):
                    try:self.trial_ledger.record(self.trial_context,expression,universe,decay,payload=payload)
                    except Exception as exc:raise IndeterminateAttemptError("Accepted receipt saved; shared trial counter needs offline reconciliation") from exc
            if poll_url:
                parsed=urlparse(poll_url);base=urlparse(config.WQ_BASE_URL)
                if parsed.scheme:
                    if parsed.scheme!="https" or parsed.netloc!=base.netloc:
                        raise IndeterminateAttemptError("Poll receipt points outside the configured API; do not forward credentials")
                    poll_endpoint=parsed.path+("?"+parsed.query if parsed.query else "")
                elif poll_url.startswith("/") and not poll_url.startswith("//"):poll_endpoint=poll_url
                else:raise IndeterminateAttemptError("Invalid poll receipt")
            loop = asyncio.get_event_loop()
            deadline = loop.time() + config.SIMULATION_POLL_TIMEOUT_SECS
            while not alpha_id and loop.time() < deadline:
                await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
                if ledger:ledger.reserve_poll(attempt["attempt_id"],getattr(config,"MAX_POLL_OPERATIONS",1000))
                try:
                    remaining=(json.loads(attempt["receipt"])["deadline_epoch"]-time.time()) if ledger and attempt.get("receipt") else None
                    if ledger and remaining is None:
                        # Newly accepted receipt is in the ledger, not the old
                        # prepare() snapshot; use the original acceptance deadline.
                        current_attempt=ledger.prepare(payload,self.experiment_context)
                        remaining=json.loads(current_attempt["receipt"])["deadline_epoch"]-time.time()
                    poll = await asyncio.wait_for(self.network.request("GET",poll_endpoint),timeout=max(.001,remaining)) if ledger else await self.network.request("GET",poll_endpoint)
                except AuthenticationError:raise
                except Exception as exc:
                    if ledger:raise IndeterminateAttemptError("Accepted poll failed/bounded out; preserve receipt and original deadline") from exc
                    raise
                pbody = poll.get("json") or {}
                status = str(pbody.get("status", "")).upper()
                if status in ("ERROR", "FAIL", "FAILED"):
                    errored = True
                    if ledger:ledger.reject(attempt["attempt_id"],"remote "+status)
                    break
                if status == "COMPLETE" or pbody.get("alpha"):
                    alpha_id = pbody.get("alpha")
                    if ledger and alpha_id:ledger.remote_complete(attempt["attempt_id"],alpha_id)
                    break

        if not alpha_id:
            if ledger and not errored:
                # Record unresolved state even when the local loop deadline
                # closes between polls. Never refund/repost this remote job.
                ledger.transition(attempt["attempt_id"],{"accepted"},"expired_unresolved",{"reason":"local polling loop expired"})
                raise IndeterminateAttemptError("Accepted job remains unresolved after deadline")
            # Cache genuine errors so we don't retry a broken expression, but do
            # NOT cache timeouts (those may succeed on a later, calmer run).
            if errored:
                self.result_cache[cache_key] = result
            return result

        detail = await self.network.request("GET", f"/alphas/{alpha_id}")
        detail_json = detail.get("json") or {}
        metrics = detail_json.get("is") or {}
        if detail.get("status_code")!=200 or not isinstance(metrics,dict) or any(self._safe_float(metrics.get(k),None) is None for k in ("sharpe","turnover","returns")):
            raise RuntimeError("Completed alpha detail is unavailable/malformed; retain receipt and recover via GET, not a new simulation")
        result.alpha_id = alpha_id
        result.sharpe = self._safe_float(metrics.get("sharpe"), 0.0)
        result.turnover = self._safe_float(metrics.get("turnover"), 1.0)
        result.returns = self._safe_float(metrics.get("returns"), 0.0)
        result.skew = self._safe_float(metrics.get("skewness"), 0.0)
        result.kurtosis = self._safe_float(metrics.get("kurtosis"), 0.0)
        # Missing risk evidence remains unknown and fails a configured gate;
        # an absent drawdown/margin is not a fabricated zero-risk observation.
        result.drawdown = self._safe_float(metrics.get("drawdown"), None)
        result.margin = self._safe_float(metrics.get("margin"), None)
        # BRAIN submittability checks (is.checks): names of any gate BRAIN itself
        # FAILED (concentration, sub-universe Sharpe, turnover floor, ...) -- the
        # failures our own metric thresholds can't see. PENDING submission-time
        # checks (self-correlation) are not failures and are excluded.
        evidence = parse_checks(metrics)
        result.failed_checks = self._failed_check_names(metrics)
        result.sharpe_2y = evidence.sharpe_2y
        result.pnl_realization = evidence.pnl_realization
        result.pyramid_multiplier = evidence.pyramid_multiplier
        trl = metrics.get("trackRecordLength")  # longCount is a position count, not a time sample size
        result.track_record_length = int(trl) if trl else config.DEFAULT_TRACK_RECORD_LENGTH
        # Out-of-sample Sharpe when the platform reports it (Upgrade #6). Stays
        # None for fresh sims with no OOS window yet, keeping the penalty neutral.
        os_metrics = detail_json.get("os") or {}
        oos_sharpe = os_metrics.get("sharpe")
        result.oos_sharpe = self._safe_float(oos_sharpe, None) if oos_sharpe is not None else None
        result.valid = True
        if ledger:ledger.complete(attempt["attempt_id"],asdict(result),metrics)
        await self._persist_raw_result(result,payload,metrics)
        # Persist the raw result the INSTANT it completes (incremental + crash-
        # safe). A simulation that finished on WorldQuant must survive even if the
        # run is interrupted before this whole generation's gather() returns --
        # otherwise completed sims that already cost quota silently vanish and the
        # DB looks frozen (e.g. stuck at 197). fitness / is_qualified /
        # max_correlation are still unknown here (they need the generation-level
        # batch); the batch save in _evaluate_population re-saves the SAME sharpe
        # with those filled in, and the db_manager upsert's ">=" guard lets that
        # enrichment through while keeping any genuinely better later result.
        # Return-orthogonality selection lever (Option B): fetch this alpha's
        # daily PnL so _evaluate_population can damp the fitness of candidates
        # whose RETURNS merely re-express the elite basket (raising ENB). Bounded
        # to genuinely strong alphas (the only ones that become elites/parents)
        # so the extra PnL GETs can't swamp the throttled queue. Off by default;
        # enabled for run_4 via WQ_RETURN_DECORR_SELECTION=1. Degrades to neutral
        # if PnL is unavailable, so it can never block or crash an alpha.
        if (getattr(config, "RETURN_DECORR_SELECTION_ENABLED", False)
                and result.sharpe >= getattr(config, "RETURN_DECORR_MIN_SHARPE", 1.0)):
            try:
                pnl_series = await self._fetch_alpha_pnl(alpha_id)
            except Exception as e:
                pnl_series = []
                logger.warning(f"PnL fetch errored for {alpha_id}: {e}")
            if pnl_series:
                self._pnl_by_alpha_id[alpha_id] = dict(pnl_series)
                try:
                    await self.db.save_pnl(alpha_id, pnl_series)
                except Exception as e:
                    logger.warning(f"Could not persist PnL for {alpha_id}: {e}")
        self.result_cache[cache_key] = result
        return result

    async def _persist_raw_result(self,result,payload,metrics):
        # Receipt ledger completion survives a failure of this derived DB save.
        await self.db.save_checks(result.alpha_id,metrics)
        await self.db.save_evidence(result.alpha_id,asdict(result),payload)
        await self.db.save_alpha(result.expression,result.universe,result.decay,result.alpha_id,
            self.generation,result.sharpe,result.turnover,None,_ast_depth(result.expression),
            result.skew,result.kurtosis,result.track_record_length,None,
            returns=result.returns,oos_sharpe=result.oos_sharpe,is_qualified=0,failed_checks=result.failed_checks)

    # --- risk gates (C9) -----------------------------------------------------
    def _passes_risk_gates(self, r) -> bool:
        """True unless an alpha trips a hard risk gate BRAIN would reject on:
        excessive IS max drawdown or non-positive margin. Both thresholds are
        config knobs; a None threshold (or DRAWDOWN_MARGIN_GATE_ENABLED=False)
        disables that check. Missing evidence fails a configured gate."""
        if not getattr(config, "DRAWDOWN_MARGIN_GATE_ENABLED", True):
            return True
        max_dd = getattr(config, "MAX_DRAWDOWN", None)
        if max_dd is not None and (r.drawdown is None or abs(r.drawdown) > max_dd):
            return False
        min_margin = getattr(config, "MIN_MARGIN", None)
        if min_margin is not None and (r.margin is None or r.margin < min_margin):
            return False
        return True

    def _risk_fail_reason(self, r) -> str:
        max_dd = getattr(config, "MAX_DRAWDOWN", None)
        if max_dd is not None and r.drawdown is None:return "unknown_drawdown"
        if max_dd is not None and abs(r.drawdown) > max_dd:
            return f"high_drawdown ({abs(r.drawdown):.2f} > {max_dd})"
        min_margin = getattr(config, "MIN_MARGIN", None)
        if min_margin is not None and r.margin is None:return "unknown_margin"
        if min_margin is not None and r.margin < min_margin:
            return f"low_margin ({r.margin:.5f} < {min_margin})"
        return "risk_gate"

    # --- BRAIN submittability-checks gate (is.checks) ------------------------
    @staticmethod
    def _failed_check_names(metrics) -> str:
        """Comma-joined names of BRAIN is.checks whose result is FAIL/ERROR. These
        are the gates BRAIN itself would reject on (concentration, sub-universe
        Sharpe, turnover floor, ...). PENDING (submission-time) checks are NOT
        failures, so a not-yet-submitted alpha is never falsely flagged. Returns
        CHECKS_UNVERIFIABLE when evidence is missing/unknown."""
        evidence = parse_checks(metrics)
        if not evidence.verified:
            return "CHECKS_UNVERIFIABLE"
        return ",".join(evidence.failed)

    def _passes_checks_gate(self, r) -> bool:
        """True unless BRAIN's own is.checks flagged a blocking FAIL. Fails CLOSED
        when platform checks are missing or have unknown result states. Disabled when
        CHECKS_GATE_ENABLED is off."""
        if not getattr(config, "CHECKS_GATE_ENABLED", True):
            return True
        return not getattr(r, "failed_checks", "")

    async def _check_correlation(self, alpha_id) -> float:
        """Realized self-correlation (max abs) from the platform. This is the
        authoritative decorrelation signal, unlike the structural string proxy.

        FAILS CLOSED. A SUCCESSFUL response with no correlation records means the
        alpha genuinely has nothing to correlate against yet -> 0.0 (legitimately
        decorrelated, so the first winners are never blocked). But a network /
        parse FAILURE must NOT be read as \"perfectly decorrelated\": that let an
        unverifiable alpha sail through the correlation gate and possibly get
        submitted. We retry a few times (the rate limiter still applies) and, if
        every attempt fails, return a max-correlation of 1.0 so the caller treats
        the alpha as correlated and WITHHOLDS promotion rather than submitting
        something we could not actually check."""
        if not alpha_id:
            return None
        attempts = max(1, getattr(config, "CORRELATION_CHECK_ATTEMPTS", 3))
        for attempt in range(attempts):
            try:
                resp = await self.network.request("GET", f"/alphas/{alpha_id}/correlations/self")
                data = resp.get("json")
                if resp.get("status_code")!=200:raise ValueError("Correlation response not successful")
                records = []
                if isinstance(data, dict):
                    records = data.get("records",data.get("results"))
                    if not isinstance(records,list):raise ValueError("Correlation response missing explicit record list")
                elif isinstance(data, list):
                    records = data
                else:raise ValueError("Malformed correlation response")
                values = []
                for row in records:
                    if isinstance(row, dict):
                        v = row.get("correlation", row.get("value", row.get("max")))
                    elif isinstance(row, (list, tuple)) and row:
                        v = row[-1]
                    else:
                        v = row
                    if isinstance(v, (int, float)) and not isinstance(v,bool) and math.isfinite(v) and abs(v)<=1:
                        values.append(abs(float(v)))
                    else:raise ValueError("Unverifiable correlation row")
                return max(values) if values else 0.0
            except Exception as e:
                logger.error(
                    f"Correlation check failed for {alpha_id} "
                    f"(attempt {attempt + 1}/{attempts}): {e}")
                if attempt + 1 < attempts:
                    await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
        # Every attempt failed -> fail CLOSED (treat as fully self-correlated).
        return None

    @staticmethod
    def _parse_pnl_records(payload):
        """Defensively extract [(date, cumulative_pnl)] from a WorldQuant pnl
        recordset (mirrors backfill_pnl._parse_pnl_records): handles both
        {records: [[date, val], ...]} and {records: [{date:.., pnl:..}, ...]}."""
        if not isinstance(payload, dict):
            return []
        records = payload.get("records") or payload.get("results") or []
        out = []
        for row in records:
            date = val = None
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                date, val = row[0], row[-1]
            elif isinstance(row, dict):
                date = row.get("date") or row.get("Date")
                val = row.get("pnl", row.get("value", row.get("PnL")))
            if date is None or val is None:
                continue
            try:
                out.append((str(date), float(val)))
            except (TypeError, ValueError):
                continue
        return out

    async def _fetch_alpha_pnl(self, alpha_id):
        """Fetch one alpha's daily PnL series, POLLING through WorldQuant's async
        recordset generation (a 200 + empty body + Retry-After is returned while
        the recordset is still building), mirroring backfill_pnl._fetch_pnl.
        Returns [(date, cumulative_pnl)] or [] on a terminal error / exhausted
        poll budget. Used only for the return-orthogonality selection lever."""
        if not alpha_id:
            return []
        target = config.WQ_PNL_ENDPOINT_TEMPLATE.format(alpha_id=alpha_id)
        attempts = max(1, getattr(config, "PNL_FETCH_MAX_ATTEMPTS", 8))
        for _ in range(attempts):
            try:
                resp = await self.network.request("GET", target)
            except Exception as e:
                logger.warning(f"PnL fetch failed for {alpha_id}: {e}")
                return []
            if resp["status_code"] not in (200, 201):
                return []
            series = self._parse_pnl_records(resp.get("json") or {})
            if series:
                return series
            # 200 but empty => still generating; follow a Location if given,
            # else re-GET after the suggested (or default) delay.
            if resp.get("location"):
                target = resp["location"].replace(config.WQ_BASE_URL, "")
            retry_after = (resp.get("headers") or {}).get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else config.SIMULATION_POLL_INTERVAL_SECS
            except (TypeError, ValueError):
                delay = config.SIMULATION_POLL_INTERVAL_SECS
            await asyncio.sleep(delay)
        return []

    async def _elite_pnl_matrix(self, elite_count):
        """Daily-PnL series for the current elite basket (population[:elite_count]),
        from the in-memory cache first and lazily from the alpha_pnl table on
        resume. Returns a list of {date: cumulative_pnl} dicts for elites that
        have PnL; an empty list disables return-orthogonality shaping for this
        batch (graceful structural-only fallback)."""
        out = []
        for rec in self.population[:elite_count]:
            aid = rec.get("alpha_id")
            if not aid:
                continue
            series = self._pnl_by_alpha_id.get(aid)
            if series is None:
                rows = await self.db.load_pnl(aid)
                if rows:
                    series = dict(rows)
                    self._pnl_by_alpha_id[aid] = series
            if series:
                out.append(series)
        return out

    async def _is_near_duplicate_loser(self, canonical) -> bool:
        if len(self.loser_exprs) < 20:
            return False
        refs = self.loser_exprs[-400:]
        # AST-motif similarity (structural) rather than the old char-ngram string
        # proxy (Upgrade #4): catches twins that merely read differently as text.
        sim = await asyncio.to_thread(self.deflation.ast_similarity, canonical, refs)
        return sim >= config.AST_DEDUP_SIMILARITY

    # --- evaluation ----------------------------------------------------------
    async def _evaluate_population(self, candidates, allow_grid=True, skip_loser_filter=False):
        prepared = []
        # PASSIVE lineage capture: candidates may carry origin / parent_id /
        # mutation_type tags (seed, ga, reseed, refine, negation, universe_sweep).
        # Key them by canonical|universe|decay here and replay them into the
        # enrichment save below, so the instrumentation columns populate WITHOUT
        # touching any selection / mutation / simulation behaviour.
        lineage_by_key = {}
        seen_batch=set()
        existing_population_keys={f'{r["expression"]}|{r["universe"]}|{r["decay"]}' for r in self.population}
        for cand in candidates:
            expr = cand.get("expression")
            if not expr:
                continue
            ok, canonical = SyntaxValidator.parse_and_validate(expr)
            if not ok or SyntaxValidator.is_tautology(canonical):
                continue
            universe = cand.get("universe") or config.PRIMARY_UNIVERSE
            decay = cand.get("decay")
            if decay is None:
                decay = random.choice(config.DECAYS)
            key = f"{canonical}|{universe}|{decay}"
            if key in seen_batch or key in existing_population_keys:continue
            seen_batch.add(key)
            if key in self.evaluated_canon and key not in self._recover_pending_keys:
                continue
            self.evaluated_canon.add(key)
            self._proposal_lineage[key]={name:cand.get(name) for name in ("origin","parent_id","mutation_type")}
            prepared.append((canonical, universe, decay))
            if cand.get("origin") or cand.get("parent_id") or cand.get("mutation_type"):
                lineage_by_key.setdefault(key, {
                    "parent_id": cand.get("parent_id"),
                    "mutation_type": cand.get("mutation_type"),
                    "origin": cand.get("origin"),
                })

        filtered = []
        for canonical, universe, decay in prepared:
            # Sign-flip ("mirror") candidates intentionally share almost their
            # entire AST with the negative-Sharpe loser they were derived from,
            # so the near-duplicate-loser guard would wrongly reject them. Skip
            # it for those (the expression|universe|decay dedup above still
            # applies, so nothing is ever double-simulated).
            if f"{canonical}|{universe}|{decay}" not in self._recover_pending_keys and not skip_loser_filter and await self._is_near_duplicate_loser(canonical):
                continue
            filtered.append((canonical, universe, decay))
        if not filtered:
            return []

        if getattr(config,"SURROGATE_PRIORITIZATION_ENABLED",False):
            from forge2_queue import prioritize
            from surrogate_prescreener import score
            filtered = prioritize(filtered,score)
        tasks = [asyncio.create_task(self._simulate_alpha(c, u, d)) for c, u, d in filtered]
        self._active_tasks.update(tasks)
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            for t in tasks:
                self._active_tasks.discard(t)

        # Fail SOFT on a per-alpha transport error. The network engine already
        # retries transport / 5xx failures; if it still gives up and RAISES on a
        # single alpha, that exception used to abort the whole asyncio.gather and
        # crash run() mid-generation. Downgrade it to a skipped alpha instead --
        # every completed sim in this batch already raw-saved itself the instant
        # it finished, so nothing durable is lost and the dedup guard skips it on
        # resume. AuthenticationError is the ONE exception we re-raise: it means
        # the session is permanently lost (the human re-auth budget was
        # exhausted), so the run should stop cleanly and resume from the
        # checkpoint once a fresh session is available rather than silently
        # booking every remaining alpha as a loser.
        clean = []
        for item in results:
            if isinstance(item, (AuthenticationError,IndeterminateAttemptError)):
                raise item
            if isinstance(item, BaseException):
                logger.warning(f"Simulation task failed; skipping alpha: {item}")
                continue
            clean.append(item)
        results = clean

        valid = [r for r in results if r.valid]
        async with self._state_lock:
            for r in results:
                if not r.valid:
                    self.loser_exprs.append(r.expression)
                    self._remember_failure(r.expression, "simulation_failed_or_rejected")
        if not valid:
            return []

        # Single fitness path. num_trials is the GLOBAL count of completed
        # simulations (the multiple-testing penalty), var_trials is the empirical
        # per-period variance of historical Sharpes.
        num_trials = max(2, self.trial_ledger.count() if getattr(self,"trial_ledger",None)
                        else await self.db.count_trials())
        var_trials = self._estimate_var_trials()
        dsr_scores = [
            self.deflation.calculate_dsr(r.sharpe, r.skew, r.kurtosis, r.track_record_length, num_trials, var_trials)
            for r in valid
        ]
        elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
        elite_exprs = [rec["expression"] for rec in self.population[:elite_count]]
        # Offload the CPU-bound TF-IDF diversity batch to a worker thread so it
        # never blocks the event loop while other simulations are polling.
        adjusted = await asyncio.to_thread(
            self.deflation.calculate_orthogonal_fitness_batch,
            [r.expression for r in valid], elite_exprs, dsr_scores,
        )
        # Return-orthogonality shaping (run_4 lever, Option B): further damp each
        # candidate's adjusted DSR by the max |PnL correlation| of its daily
        # returns to the elite basket, so selection breeds toward RETURN-
        # orthogonal alphas, not just structurally-novel ones. Neutral when
        # disabled or when PnL/overlap is unavailable, so the structural shaping
        # above is the floor behaviour.
        if getattr(config, "RETURN_DECORR_SELECTION_ENABLED", False):
            elite_pnls = await self._elite_pnl_matrix(elite_count)
            if elite_pnls:
                candidate_pnls = [self._pnl_by_alpha_id.get(r.alpha_id) for r in valid]
                adjusted = await asyncio.to_thread(
                    self.deflation.calculate_return_orthogonal_fitness_batch,
                    candidate_pnls, elite_pnls, adjusted,
                    config.RETURN_DECORR_MIN_OVERLAP, config.RETURN_DECORR_K,
                )

        new_records = []
        winner_records = []
        min_fitness = config.MIN_FITNESS_DELAY0 if config.DEFAULT_DELAY == 0 else config.MIN_FITNESS

        # First pass: fitness + the cheap promotion gates (Sharpe, turnover,
        # WorldQuant fitness). The expensive self-correlation network call is
        # deferred so qualifying alphas can be checked concurrently below.
        prelim = []
        for r, dsr, adj in zip(valid, dsr_scores, adjusted):
            depth = _ast_depth(r.expression)
            # Single shared fitness definition (see _composite_fitness) so the
            # live and resume paths can never silently diverge.
            fitness = self._composite_fitness(adj, depth, r.sharpe, r.oos_sharpe, r.expression)
            # WorldQuant headline FITNESS gate (Upgrade #1), in addition to
            # Sharpe/turnover.
            wq_fitness = config.worldquant_fitness(r.sharpe, r.returns, r.turnover)
            # turnover is band-gated: it must clear the HARD submittable floor
            # (MIN_TURNOVER, ~1% on BRAIN) as well as stay under MAX_TURNOVER.
            min_turnover = getattr(config, "MIN_TURNOVER", 0.0)
            # Risk gates (C9): reject blow-up-prone alphas BRAIN would never
            # accept (excessive max drawdown / non-positive margin) so we don't
            # waste our capped submissions on them. Disabled => always passes.
            risk_ok = self._passes_risk_gates(r)
            # BRAIN is.checks gate: an alpha BRAIN itself flagged (concentration,
            # sub-universe Sharpe, turnover floor, ...) can never qualify, no
            # matter how good our own metrics look. This is what stops the engine
            # promoting "submittable" alphas that actually fail on BRAIN.
            checks_ok = self._passes_checks_gate(r)
            qualifies = (r.sharpe >= config.MIN_SHARPE
                         and min_turnover <= r.turnover <= config.MAX_TURNOVER
                         and wq_fitness >= min_fitness
                         and risk_ok
                         and checks_ok)
            prelim.append((r, dsr, depth, fitness, wq_fitness, qualifies))

        # Fan out the self-correlation checks for qualifying alphas in parallel
        # (the NetworkEngine rate limiter still throttles them) instead of
        # awaiting them one alpha at a time.
        qual_indices = [i for i, p in enumerate(prelim) if p[5]]
        async def correlation_for(r):
            key=f"{r.expression}|{r.universe}|{r.decay}"
            if key in self._recover_pending_keys and key in self.result_cache:
                rows=await self.db.get_population_for_keys([[r.expression,r.universe,r.decay]])
                return rows[0][9]  # Missing stored correlation remains unknown, not a PASS.
            return await self._check_correlation(r.alpha_id)
        corr_values = await asyncio.gather(*[correlation_for(prelim[i][0]) for i in qual_indices])
        corr_map = dict(zip(qual_indices, corr_values))

        for i, (r, dsr, depth, fitness, wq_fitness, qualifies) in enumerate(prelim):
            max_corr = corr_map.get(i) if qualifies else None
            record = {
                "expression": r.expression, "universe": r.universe, "decay": r.decay,
                "sharpe": r.sharpe, "turnover": r.turnover, "dsr": dsr, "fitness": fitness,
                "ast_depth": depth, "skew": r.skew, "kurtosis": r.kurtosis,
                "track_record_length": r.track_record_length, "alpha_id": r.alpha_id,
                "max_correlation": max_corr, "returns": r.returns,
                "wq_fitness": wq_fitness, "oos_sharpe": r.oos_sharpe,
                "failed_checks": r.failed_checks,
                "sharpe_2y":r.sharpe_2y, "pnl_realization":r.pnl_realization,
                "pyramid_multiplier":r.pyramid_multiplier,
            }
            promoted = bool(qualifies and max_corr is not None and max_corr <= config.MAX_SELF_CORRELATION)
            record["is_qualified"] = promoted
            new_records.append(record)
            if promoted:
                winner_records.append(record)
            elif r.sharpe < getattr(config, "REFINE_SHARPE_THRESHOLD", config.MIN_SHARPE):
                record["_fail_reason"] = f"low_sharpe ({r.sharpe:.2f} < {config.MIN_SHARPE})"
            elif r.turnover > config.MAX_TURNOVER:
                record["_fail_reason"] = f"high_turnover ({r.turnover:.2f} > {config.MAX_TURNOVER})"
            elif r.turnover < getattr(config, "MIN_TURNOVER", 0.0):
                record["_fail_reason"] = f"low_turnover ({r.turnover:.3f}) [below submittable floor]"
            elif wq_fitness < min_fitness:
                record["_fail_reason"] = f"low_fitness ({wq_fitness:.2f} < {min_fitness})"
            elif not self._passes_risk_gates(r):
                record["_fail_reason"] = self._risk_fail_reason(r)
            elif getattr(r, "failed_checks", ""):
                record["_fail_reason"] = f"brain_checks_failed ({r.failed_checks})"
            elif max_corr is not None and max_corr > config.MAX_SELF_CORRELATION:
                record["_fail_reason"] = f"self_correlated ({max_corr:.2f} > {config.MAX_SELF_CORRELATION})"

        async with self._state_lock:
            for rec in new_records:
                self.population.append(rec)
                self.history_scores.append(rec["sharpe"])
                # Treat only alphas BELOW the refine threshold as losers; near-
                # winners (>= REFINE_SHARPE_THRESHOLD) are active refine targets,
                # so they must NOT poison the near-duplicate-loser guard, which
                # would otherwise reject their (identical-expression) settings-
                # tier refinements as structural duplicates.
                if rec["sharpe"] < getattr(config, "REFINE_SHARPE_THRESHOLD", config.MIN_SHARPE):
                    self.loser_exprs.append(rec["expression"])
                if rec.get("_fail_reason"):
                    self._remember_failure(rec["expression"], rec["_fail_reason"])
                _lin = lineage_by_key.get(
                    f'{rec["expression"]}|{rec["universe"]}|{rec["decay"]}', {})
                await self.db.save_alpha(
                    rec["expression"], rec["universe"], rec["decay"], rec["alpha_id"],
                    self.generation, rec["sharpe"], rec["turnover"], rec["fitness"],
                    rec["ast_depth"], rec["skew"], rec["kurtosis"],
                    rec["track_record_length"], rec["max_correlation"],
                    returns=rec.get("returns", 0.0), oos_sharpe=rec.get("oos_sharpe"),
                    is_qualified=1 if rec.get("is_qualified") else 0,
                    failed_checks=rec.get("failed_checks", ""),
                    parent_id=_lin.get("parent_id"),
                    mutation_type=_lin.get("mutation_type"),
                    origin=_lin.get("origin"),
                )

        # Success-side diversity (Upgrade #3) + portfolio overfitting diagnostic
        # (Upgrade #6).
        if winner_records:
            async with self._state_lock:
                for wrec in winner_records:
                    self.winner_exprs.append(wrec["expression"])
                self._refresh_avoid_motifs()
        self._log_pbo_diagnostic()

        if allow_grid:
            # Refine promoted winners AND "near-winners": alphas at/above the
            # (lower) REFINE_SHARPE_THRESHOLD that have NOT yet cleared the
            # MIN_SHARPE submit gate. Decoupling the refine TRIGGER from the
            # submit gate lets the dimension-targeted hill-climb actively push
            # the strong-but-subqualified cluster (e.g. Sharpe ~1.0-1.2) toward
            # submittable, instead of leaving it idle until something first
            # crosses MIN_SHARPE on its own (the old chicken-and-egg). The submit
            # gate is unchanged: near-winners are never marked is_qualified and
            # are never submitted; they only earn refinement branches.
            refine_threshold = getattr(config, "REFINE_SHARPE_THRESHOLD", config.MIN_SHARPE)
            near_winners = [
                rec for rec in new_records
                if not rec.get("is_qualified")
                and (rec.get("sharpe") or 0.0) >= refine_threshold
                and rec["expression"] not in self.refined
            ]
            # Bounded, highest-fitness-first so opening the trigger can't flood
            # the 429-throttled /simulations queue.
            near_winners.sort(key=lambda r: r.get("fitness", float("-inf")), reverse=True)
            max_near = getattr(config, "REFINE_MAX_TARGETS_PER_GEN", 6)
            if max_near >= 0:
                near_winners = near_winners[:max_near]
            for wrec in list(winner_records) + near_winners:
                if wrec["expression"] in self.refined:
                    continue
                self.refined.add(wrec["expression"])
                # Iterative local refinement; allow_grid=False inside prevents
                # unbounded recursive expansion.
                await self._refine_alpha(wrec)
            # Universe funnel: sweep each STRONG promoted winner across the other
            # universes (the GA itself only searches config.PRIMARY_UNIVERSE).
            # allow_grid=False keeps this a one-shot robustness/diversification
            # check rather than triggering nested refinement, and the
            # (expression|universe|decay) dedup guard means the primary-universe
            # row is never re-simulated.
            if getattr(config, "UNIVERSE_SWEEP_ENABLED", True):
                sweep = []
                for wrec in winner_records:
                    if (wrec.get("universe") == config.PRIMARY_UNIVERSE
                            and (wrec.get("sharpe") or 0.0) >= config.UNIVERSE_SWEEP_MIN_SHARPE):
                        sweep.extend(self._neighbors_universe_sweep(wrec))
                if sweep:
                    await self._evaluate_population(sweep, allow_grid=False)

            # Sign-flip (negation) harvest: a strongly NEGATIVE-Sharpe alpha is a
            # correct signal pointing the wrong way. Negating it flips Sharpe,
            # returns and WorldQuant fitness sign while turnover is UNCHANGED, so
            # its mirror is an equally strong POSITIVE alpha. We harvest any
            # mirror that is at least refine-worthy (mirror Sharpe >=
            # REFINE_SHARPE_THRESHOLD): a fully-qualifying mirror is promoted, and
            # a near-winner mirror is then hill-climbed toward submittable. Mirrors
            # skip the loser guard (they share their AST with the negative
            # original). A mirror is positive-Sharpe, so it is never itself
            # re-negated -- no ping-pong.
            if getattr(config, "NEGATION_ENABLED", True):
                negations = []
                seen_neg = set()
                for rec in new_records:
                    sharpe = rec.get("sharpe")
                    if sharpe is None or rec.get("is_qualified"):
                        continue
                    mirror_sharpe = -sharpe
                    # Harvest any mirror that is at least REFINE-WORTHY, not just
                    # immediately submittable: a mirror Sharpe in
                    # [REFINE_SHARPE_THRESHOLD, MIN_SHARPE) is a near-winner that
                    # the (allow_grid=True) refinement pass below can hill-climb
                    # toward submittable -- exactly the "flip it, THEN make it
                    # better" case. We deliberately do NOT pre-gate on turnover or
                    # WQ fitness here: those are the very axes refinement attacks,
                    # and the mirror's own simulation makes the real promotion
                    # decision. Below REFINE_SHARPE_THRESHOLD refinement never
                    # engages, so flipping would only yield a weak GA parent at the
                    # cost of a throttled simulation -- not worth it.
                    if mirror_sharpe < refine_threshold:
                        continue
                    mirror = _negate_expression(rec["expression"])
                    if not mirror:
                        continue
                    key = f"{mirror}|{rec['universe']}|{rec['decay']}"
                    if key in self.evaluated_canon or key in seen_neg:
                        continue
                    seen_neg.add(key)
                    negations.append({"expression": mirror, "universe": rec["universe"],
                                      "decay": rec["decay"], "_mirror_sharpe": mirror_sharpe,
                                      "origin": "negation",
                                      "parent_id": rec.get("alpha_id") or None,
                                      "mutation_type": "negation"})
                # Highest expected (mirror) Sharpe first, then bound the batch so
                # the harvest can't overwhelm the throttled /simulations queue.
                negations.sort(key=lambda c: c.get("_mirror_sharpe", 0.0), reverse=True)
                max_neg = getattr(config, "NEGATION_MAX_PER_GEN", 8)
                if max_neg >= 0:
                    negations = negations[:max_neg]
                for c in negations:
                    c.pop("_mirror_sharpe", None)
                if negations:
                    # allow_grid=True so a harvested mirror is treated like any
                    # other fresh candidate: a fully-qualifying mirror is promoted
                    # + universe-swept, and a near-winner mirror is refined toward
                    # submittable. No ping-pong: a mirror is positive-Sharpe, so
                    # its own mirror is negative and fails the threshold above.
                    await self._evaluate_population(negations, allow_grid=True,
                                                    skip_loser_filter=True)

        return new_records

    # --- inline refinement (local hill-climb on promoted winners) -----------
    async def _refine_alpha(self, seed_record):
        """Take a freshly-promoted winner and iteratively branch it, each round
        ATTACKING ITS WEAKEST DIMENSION (turnover / Sharpe / correlation) chosen
        by a softmax over the per-axis health scores (Upgrade #5). This spends
        the branch budget where promotion is actually blocked instead of a fixed
        tier order. Stops on a hard branch cap OR a multi-round plateau. Every
        branch is a real simulation, so it still counts toward the
        Deflated-Sharpe multiple-testing penalty and cannot curve-fit past it.
        """
        if not config.REFINEMENT_ENABLED:
            return
        best = seed_record
        branches_used = 0
        stale_rounds = 0
        max_stale = max(3, config.REFINE_PATIENCE * 3)
        while branches_used < config.REFINE_MAX_BRANCHES and stale_rounds < max_stale:
            budget = config.REFINE_MAX_BRANCHES - branches_used
            dimension = self._pick_target_dimension(best, config.REFINE_TEMPERATURE)
            candidates = self._neighbors_for_dimension(dimension, best)[: min(budget, config.REFINE_BATCH_SIZE)]
            if not candidates:
                stale_rounds += 1
                continue
            # PASSIVE lineage tags: which winner was hill-climbed, on which axis.
            for _c in candidates:
                _c.setdefault("origin", "refine")
                _c.setdefault("parent_id", best.get("alpha_id") or None)
                _c.setdefault("mutation_type", f"refine:{dimension}")
            branches_used += len(candidates)
            records = await self._evaluate_population(candidates, allow_grid=False)
            improved = False
            for rec in records:
                if rec["fitness"] > best["fitness"] + config.REFINE_MIN_IMPROVEMENT:
                    best = rec
                    improved = True
            stale_rounds = 0 if improved else stale_rounds + 1
        if best is not seed_record:
            logger.info(
                f"Refined alpha: fitness {seed_record['fitness']:.4f} -> {best['fitness']:.4f} "
                f"(sharpe {seed_record['sharpe']:.3f} -> {best['sharpe']:.3f}) "
                f"over {branches_used} branch(es)."
            )

    # --- dimension-targeted refinement helpers (Upgrade #5) ------------------
    def _dimension_scores(self, rec):
        """Per-axis 'health' in roughly comparable units; higher = healthier. The
        lowest score is the alpha's weakest dimension."""
        sharpe = rec.get("sharpe", 0.0) or 0.0
        turnover = rec.get("turnover", 1.0)
        corr = rec.get("max_correlation")
        e_sharpe = sharpe / max(config.MIN_SHARPE, 1e-9)
        # Turnover health peaks INSIDE the band; it drops on both sides so the
        # weakest-dimension picker attacks turnover only when it is out of band.
        target_low = getattr(config, "TURNOVER_TARGET_LOW", 0.0)
        min_turn = getattr(config, "MIN_TURNOVER", 0.0)
        if turnover < target_low:
            # Too low (incl. below the hard submittable floor) -> UNHEALTHY axis,
            # so refinement attacks it and trades turnover UP for Sharpe instead
            # of treating "ever lower" as ever better.
            e_turnover = (turnover - min_turn) / max(target_low - min_turn, 1e-9)
        elif turnover > config.MAX_TURNOVER:
            # Too high -> unhealthy; refinement slows the signal down.
            e_turnover = (config.MAX_TURNOVER - turnover) / max(config.MAX_TURNOVER, 1e-9)
        else:
            e_turnover = 1.0  # inside the healthy band: not the axis to attack
        e_corr = 1.0 if corr is None else (config.MAX_SELF_CORRELATION - corr) / max(config.MAX_SELF_CORRELATION, 1e-9)
        scores = {"sharpe": e_sharpe, "turnover": e_turnover, "correlation": e_corr}
        if rec.get("sharpe_2y") is not None:
            scores["recency"] = rec["sharpe_2y"] / 1.58
        if rec.get("pnl_realization") is not None:
            scores["realization"] = rec["pnl_realization"] / 20.0
        return scores

    def _pick_target_dimension(self, rec, temperature=1.0):
        scores = self._dimension_scores(rec)
        dims = list(scores)
        e_max = max(scores.values())
        t = max(float(temperature), 1e-6)
        weights = [math.exp((e_max - scores[d]) / t) for d in dims]
        if sum(weights) <= 0:
            return random.choice(dims)
        return random.choices(dims, weights=weights, k=1)[0]

    def _neighbors_for_dimension(self, dimension, rec):
        if dimension == "turnover":
            cands = self._neighbors_turnover(rec)
        elif dimension == "correlation":
            cands = self._neighbors_decorrelate(rec)
        elif dimension in ("recency", "realization"):
            from forge2_expression import window_neighbors
            direction = "shorter" if dimension == "recency" else "longer"
            cands = [{"expression":expr,"universe":rec["universe"],"decay":rec["decay"]}
                     for expr in window_neighbors(rec["expression"],direction)]
            if dimension == "realization":
                cands += self._neighbors_turnover(rec)
        else:  # "sharpe"
            cands = self._neighbors_wraps(rec)
        if not cands:  # fall back to the cheap, always-available settings tier
            cands = self._neighbors_settings(rec)
        return cands

    # Turnover OUT of the healthy band -> push it back toward the band. Direction
    # depends on which side it is on:
    #   * too LOW (< TURNOVER_TARGET_LOW): speed the signal UP to win Sharpe --
    #     lower the decay, SHORTEN windows, and strip a turnover gate if present.
    #     This is the "sacrifice the tiny turnover to boost Sharpe" lever.
    #   * otherwise (too high / in-band fallback): slow it DOWN -- raise decay,
    #     lengthen windows, add a trade_when/keep gate.
    def _neighbors_turnover(self, rec):
        expr = rec["expression"]
        target_low = getattr(config, "TURNOVER_TARGET_LOW", 0.0)
        raise_turnover = (rec.get("turnover") or 0.0) < target_low
        cands = []
        try:
            tree = ast.parse(expr, mode="eval")
        except Exception:
            tree = None
        consts = []
        if tree is not None:
            consts = [n for n in ast.walk(tree)
                      if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
        pool = sorted(set(_SHORT_LOOKBACKS + _LONG_LOOKBACKS))
        if raise_turnover:
            # Faster decay (toward 0) makes the book react sooner -> more turnover.
            if rec["decay"] in config.DECAYS:
                i = config.DECAYS.index(rec["decay"])
                for j in (i - 1, i - 2):
                    if j >= 0:
                        cands.append({"expression": expr, "universe": rec["universe"], "decay": config.DECAYS[j]})
            # Shorten lookbacks: a snappier signal rebalances more often.
            for idx in range(min(len(consts), 4)):
                smaller = [p for p in pool if p < consts[idx].value]
                if smaller:
                    variant = self._replace_nth_int(expr, idx, max(smaller))
                    if variant:
                        cands.append({"expression": variant, "universe": rec["universe"], "decay": rec["decay"]})
            # Sharpe-preserving lift FIRST: swap a flat ts_mean smoother for
            # ts_decay_linear over the same window so turnover rises while the
            # long-horizon signal (and its Sharpe / drawdown) is kept. Refinement
            # keeps the highest-fitness variant that clears the floor, so this
            # gentle lever beats a window-slash that tanks Sharpe whenever it works.
            decayed = _swap_smoother_to_decay(expr)
            if decayed and decayed != expr:
                cands.append({"expression": decayed, "universe": rec["universe"], "decay": rec["decay"]})
            # Un-gate: drop a trade_when/keep throttle so the signal can trade
            # every day (the inverse of the gate lever in the slow-down branch).
            ungated = _strip_turnover_gate(expr)
            if ungated and ungated != expr:
                cands.append({"expression": ungated, "universe": rec["universe"], "decay": rec["decay"]})
        else:
            # Slower decay damps churn.
            if rec["decay"] in config.DECAYS:
                i = config.DECAYS.index(rec["decay"])
                for j in (i + 1, i + 2):
                    if j < len(config.DECAYS):
                        cands.append({"expression": expr, "universe": rec["universe"], "decay": config.DECAYS[j]})
            # Lengthen lookbacks.
            for idx in range(min(len(consts), 4)):
                larger = [p for p in pool if p > consts[idx].value]
                if larger:
                    variant = self._replace_nth_int(expr, idx, min(larger))
                    if variant:
                        cands.append({"expression": variant, "universe": rec["universe"], "decay": rec["decay"]})
            # WorldQuant turnover lever: gate re-trading behind a regime condition
            # so the signal stops churning every day.
            gated = self.genetic._mutate_gate_turnover(expr)
            if gated and gated != expr:
                cands.append({"expression": gated, "universe": rec["universe"], "decay": rec["decay"]})
        return cands

    # Correlation too high -> change WHAT the signal looks at: swap fields and
    # graft new subtrees, leaving settings alone.
    def _neighbors_decorrelate(self, rec):
        expr = rec["expression"]
        cands = []
        seen = set()
        for _ in range(config.REFINE_BATCH_SIZE * 2):
            for mut in (self.genetic._mutate_field, self.genetic._mutate_wrap_ts, self.genetic._mutate_spread):
                try:
                    variant = mut(expr)
                except Exception:
                    variant = None
                if variant and variant != expr and variant not in seen:
                    seen.add(variant)
                    cands.append({"expression": variant, "universe": rec["universe"], "decay": rec["decay"]})
        return cands

    # Tier 1: settings -- highest-ROI, lowest-overfitting lever (decay,
    # universe, neutralization). Changes risk/turnover without adding any
    # expression complexity, so it is tried first.
    def _neighbors_settings(self, rec):
        expr = rec["expression"]
        cands = []
        if rec["decay"] in config.DECAYS:
            i = config.DECAYS.index(rec["decay"])
            for j in (i - 1, i + 1):
                if 0 <= j < len(config.DECAYS):
                    cands.append({"expression": expr, "universe": rec["universe"], "decay": config.DECAYS[j]})
        if rec["universe"] in config.UNIVERSES:
            i = config.UNIVERSES.index(rec["universe"])
            for j in (i - 1, i + 1):
                if 0 <= j < len(config.UNIVERSES):
                    cands.append({"expression": expr, "universe": config.UNIVERSES[j], "decay": rec["decay"]})
        inner, group = _split_group_neutralize(expr)
        if inner is not None:
            for n in config.NEUTRALIZATIONS:
                if n != group:
                    cands.append({"expression": f"group_neutralize({inner}, {n})",
                                  "universe": rec["universe"], "decay": rec["decay"]})
        return cands

    # Universe funnel: the SAME expression + decay on every OTHER universe. Used
    # to promote a winner found on the primary universe outward (TOP3000 ->
    # TOP1000 / TOP500 / TOP200) so we learn where it is strongest and collect
    # lightly-decorrelated submittable variants. The already-evaluated primary
    # row is skipped by the dedup guard, so it is never re-simulated.
    def _neighbors_universe_sweep(self, rec):
        expr = rec["expression"]
        cands = []
        for uni in config.UNIVERSES:
            if uni == rec.get("universe"):
                continue
            cands.append({"expression": expr, "universe": uni, "decay": rec["decay"],
                          "origin": "universe_sweep",
                          "parent_id": rec.get("alpha_id") or None,
                          "mutation_type": "universe_sweep"})
        return cands

    @staticmethod
    def _replace_nth_int(expression, n_index, new_value):
        try:
            tree = ast.parse(expression, mode="eval")
        except Exception:
            return None
        consts = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
        if n_index >= len(consts):
            return None
        consts[n_index].value = new_value
        try:
            return ast.unparse(tree)
        except Exception:
            return None

    # Tier 3: operator wraps / swaps -- the most aggressive, most overfitting-
    # prone axis, reused from the genetic operators. Only reached after both
    # settings and windows plateau.
    def _neighbors_wraps(self, rec):
        expr = rec["expression"]
        cands = []
        seen = set()
        for _ in range(config.REFINE_BATCH_SIZE * 2):
            for mut in (self.genetic._mutate_wrap_ts, self.genetic._mutate_operator):
                try:
                    variant = mut(expr)
                except Exception:
                    variant = None
                if variant and variant != expr and variant not in seen:
                    seen.add(variant)
                    cands.append({"expression": variant, "universe": rec["universe"], "decay": rec["decay"]})
        return cands

    def _enforce_skeleton_diversity(self, ordered):
        """Monoculture breaker: cap how many population members may share one
        structural skeleton. Walks the NSGA-II-ordered list best-first and, once a
        skeleton already fills SKELETON_MAX_FRACTION of POPULATION_SIZE, pushes
        further members of that skeleton to the TAIL so they fall off the
        [:POPULATION_SIZE] truncation FIRST. This only REORDERS survivors -- it
        never shrinks the pool below its target -- so diverse shapes are
        guaranteed room to breed even before any alpha qualifies (FSA, by
        contrast, only engages once winners exist). Disabled when the fraction is
        >= 1."""
        frac = getattr(config, "SKELETON_MAX_FRACTION", 1.0)
        if frac >= 1.0 or not ordered:
            return ordered
        cap = max(1, int(config.POPULATION_SIZE * frac))
        counts = Counter()
        kept, overflow = [], []
        for rec in ordered:
            skel = _alpha_skeleton(rec.get("expression", ""))
            if counts[skel] < cap:
                counts[skel] += 1
                kept.append(rec)
            else:
                overflow.append(rec)
        return kept + overflow

    def _enforce_field_diversity(self, ordered):
        """Field-level monoculture breaker (complements the skeleton cap, which is
        blind to fields). Walks the NSGA-II-ordered list best-first and, once a
        single DOMINANT data field already fills FIELD_DIVERSITY_MAX_FRACTION of
        POPULATION_SIZE, pushes further members relying on that same field to the
        TAIL so they fall off the [:POPULATION_SIZE] truncation first. This keeps
        field breadth alive THROUGH selection -- so two high-fitness fields (e.g.
        the observed implied-vol pair) can't crowd out the whole pool and breed a
        correlated offspring family. Only reorders survivors; never shrinks the
        pool. Disabled when the fraction is >= 1."""
        frac = getattr(config, "FIELD_DIVERSITY_MAX_FRACTION", 1.0)
        if frac >= 1.0 or not ordered:
            return ordered
        field_set = getattr(self.genetic, "_field_set", set())
        if not field_set:
            return ordered
        cap = max(1, int(config.POPULATION_SIZE * frac))
        counts = Counter()
        kept, overflow = [], []
        for rec in ordered:
            field = _dominant_field(rec.get("expression", ""), field_set)
            if field is None:
                kept.append(rec)  # no identifiable field -> never crowd-capped
                continue
            if counts[field] < cap:
                counts[field] += 1
                kept.append(rec)
            else:
                overflow.append(rec)
        return kept + overflow

    async def _select_generation_survivors(self):
        ordered=self._enforce_field_diversity(self._enforce_skeleton_diversity(self._nsga_ii_sort(self.population)))
        size=config.POPULATION_SIZE
        if not getattr(config,"BASKET_SELECTION_ENABLED",False):return ordered[:size]
        primary=[r for r in ordered if r.get("universe")==config.PRIMARY_UNIVERSE][:max(size*3,100)]
        if len(primary)<2:
            self.basket_report={"reason":"insufficient_primary_regime; base ranking retained"}
            return ordered[:size]
        pnls={}
        for r in primary:
            aid=r.get("alpha_id")
            if not aid:continue
            series=self._pnl_by_alpha_id.get(aid)
            if series is None:
                rows=await self.db.load_pnl(aid)
                series=dict(rows) if rows else None
                if series:self._pnl_by_alpha_id[aid]=series
            if series:pnls[aid]=series
        from forge2_portfolio import select_basket
        selected,report=select_basket(primary,pnls,getattr(config,"FIELD_METADATA",{}),size,
            min_overlap=config.BASKET_MIN_OVERLAP,max_abs_correlation=config.BASKET_MAX_CORRELATION,
            min_residual_fraction=config.BASKET_MIN_RESIDUAL,max_dataset_fraction=config.BASKET_DATASET_FRACTION,
            explore_fraction=config.BASKET_EXPLORATION_FRACTION)
        if "base ranking retained" in report["reason"]:
            # No financial-diversity claim. Preserve base behavior including
            # other universes when evidence cannot support a measured basket.
            self.basket_report=report
            return ordered[:size]
        report["region"]=config.DEFAULT_REGION;report["delay"]=config.DEFAULT_DELAY
        report["universe"]=config.PRIMARY_UNIVERSE
        self.basket_report=report
        return selected

    # --- selection -----------------------------------------------------------
    def _nsga_ii_sort(self, population):
        n = len(population)
        if n <= 1:
            for r in population:
                r["rank"] = 0
                r["distance"] = float("inf")
            return list(population)

        # Turnover is a target-BAND objective, not "lower is always better": clamp
        # it at TURNOVER_TARGET_LOW so NSGA-II stops rewarding the race to zero
        # (which collapsed the population onto ultra-low-turnover, highly
        # self-correlated slow-data alphas). Within [TARGET_LOW, MAX] lower
        # turnover still wins on this axis; below TARGET_LOW all alphas tie here,
        # so Sharpe/fitness decides and refinement is free to trade the sub-band
        # turnover up for Sharpe. The hard MIN_TURNOVER floor is enforced at the
        # qualification/submission gates, not here.
        turnover_floor = getattr(config, "TURNOVER_TARGET_LOW", 0.0)
        objectives = [(r.get("fitness", float("-inf")),
                       -max(r.get("turnover",1.0),turnover_floor)) for r in population]
        if getattr(config,"THIRD_OBJECTIVE_ENABLED",False):
            objectives = [(*obj,r.get("expected_value",0.0)) for obj,r in zip(objectives,population)]
        objs = objectives

        def dominates(i,j):
            return all(a>=b for a,b in zip(objs[i],objs[j])) and any(a>b for a,b in zip(objs[i],objs[j]))

        dominated = [[] for _ in range(n)]
        dom_count = [0] * n
        fronts = [[]]
        for p in range(n):
            for q in range(n):
                if p == q:
                    continue
                if dominates(p, q):
                    dominated[p].append(q)
                elif dominates(q, p):
                    dom_count[p] += 1
            if dom_count[p] == 0:
                population[p]["rank"] = 0
                fronts[0].append(p)

        i = 0
        while fronts[i]:
            nxt = []
            for p in fronts[i]:
                for q in dominated[p]:
                    dom_count[q] -= 1
                    if dom_count[q] == 0:
                        population[q]["rank"] = i + 1
                        nxt.append(q)
            i += 1
            fronts.append(nxt)
        fronts.pop()

        for r in population:
            r["distance"] = 0.0
        for front in fronts:
            if not front:
                continue
            for m in range(len(objs[0])):
                front.sort(key=lambda idx: objs[idx][m])
                population[front[0]]["distance"] = float("inf")
                population[front[-1]]["distance"] = float("inf")
                lo = objs[front[0]][m]
                hi = objs[front[-1]][m]
                span = hi - lo
                if span == 0:
                    continue
                for k in range(1, len(front) - 1):
                    population[front[k]]["distance"] += (objs[front[k + 1]][m] - objs[front[k - 1]][m]) / span

        ordered = []
        for front in fronts:
            front.sort(key=lambda idx: -population[idx]["distance"])
            ordered.extend(front)
        return [population[idx] for idx in ordered]

    def _select_parents(self):
        if len(self.population) < 2:
            return None
        def tournament():
            k = min(config.TOURNAMENT_SIZE, len(self.population))
            contenders = random.sample(self.population, k)
            return min(contenders, key=lambda r: (r.get("rank", 0), -r.get("distance", 0.0)))
        return tournament(), tournament()

    # --- bootstrap & main loop ----------------------------------------------
    async def _harvest_resumed_negatives(self):
        """One-time startup sign-flip harvest over RESUMED alphas. The live
        negation harvest only runs on freshly-evaluated candidates inside
        _evaluate_population, so strongly-NEGATIVE alphas already sitting in the
        database (loaded straight into self.population on resume) would never be
        mirrored -- their equally-strong POSITIVE twin would stay undiscovered,
        and on a run where almost nothing clears the bar that is the single
        biggest pool of ready-made winners we are leaving on the table. This
        scans the resumed population for alphas whose NEGATED Sharpe would be at
        least refine-worthy (original Sharpe <= -REFINE_SHARPE_THRESHOLD), builds
        the validated mirror group_neutralize(-signal, GROUP), and evaluates the
        mirrors with allow_grid=True so a qualifying mirror is promoted and a
        near-winner mirror is hill-climbed toward submittable. Bounded + deduped
        (via evaluated_canon) so it can't flood the 429-throttled queue; mirrors
        skip the loser guard since they share their AST with the negative
        original. A mirror is positive-Sharpe, so it is never itself re-negated."""
        if not getattr(config, "NEGATION_ENABLED", True):
            return
        if not getattr(config, "NEGATION_RESUME_ENABLED", True):
            return
        refine_threshold = getattr(config, "REFINE_SHARPE_THRESHOLD", config.MIN_SHARPE)
        negations = []
        seen_neg = set()
        for rec in self.population:
            sharpe = rec.get("sharpe")
            if sharpe is None:
                continue
            mirror_sharpe = -sharpe
            if mirror_sharpe < refine_threshold:
                continue
            mirror = _negate_expression(rec["expression"])
            if not mirror:
                continue
            key = f"{mirror}|{rec['universe']}|{rec['decay']}"
            if key in self.evaluated_canon or key in seen_neg:
                continue
            seen_neg.add(key)
            negations.append({"expression": mirror, "universe": rec["universe"],
                              "decay": rec["decay"], "_mirror_sharpe": mirror_sharpe,
                              "origin": "negation_resume",
                              "parent_id": rec.get("alpha_id") or None,
                              "mutation_type": "negation"})
        if not negations:
            return
        negations.sort(key=lambda c: c.get("_mirror_sharpe", 0.0), reverse=True)
        max_neg = getattr(config, "NEGATION_RESUME_MAX",
                          getattr(config, "NEGATION_MAX_PER_GEN", 8))
        if max_neg >= 0:
            negations = negations[:max_neg]
        for c in negations:
            c.pop("_mirror_sharpe", None)
        logger.info(
            f"Startup negation harvest: mirroring {len(negations)} resumed "
            f"negative-Sharpe alpha(s) into positive twins.")
        await self._evaluate_population(negations, allow_grid=True, skip_loser_filter=True)

    async def _refine_resumed_winners(self):
        """One-time startup hill-climb on the BEST resumed alphas. Members loaded
        from the database during resume go straight into self.population WITHOUT
        passing through _evaluate_population, so (unlike freshly-evaluated
        candidates) they never trigger inline refinement -- a strong 1.0+ resumed
        alpha would otherwise only act as a crossover/mutation parent. This pass
        branches the top resumed winners / near-winners immediately so an
        existing strong cluster keeps improving from generation 0. Bounded and
        deduped via self.refined so it can't flood the 429-throttled
        /simulations queue; a no-op when refinement is disabled."""
        if not getattr(config, "STARTUP_REFINE_ENABLED", True) or not config.REFINEMENT_ENABLED:
            return
        refine_threshold = getattr(config, "REFINE_SHARPE_THRESHOLD", config.MIN_SHARPE)
        targets = [
            rec for rec in self.population
            if (rec.get("sharpe") or 0.0) >= refine_threshold
            and rec["expression"] not in self.refined
        ]
        if not targets:
            return
        # Highest-fitness-first, then bound so opening this pass can't overwhelm
        # the throttled /simulations queue on resume.
        targets.sort(key=lambda r: r.get("fitness", float("-inf")), reverse=True)
        max_targets = getattr(config, "STARTUP_REFINE_MAX_TARGETS", 6)
        if max_targets >= 0:
            targets = targets[:max_targets]
        if not targets:
            return
        logger.info(f"Startup refinement: hill-climbing {len(targets)} resumed winner(s).")
        for rec in targets:
            if rec["expression"] in self.refined:
                continue
            self.refined.add(rec["expression"])
            await self._refine_alpha(rec)

    async def _bootstrap_population(self):
        if self._resume_population_snapshot is not None:
            # Versioned decision/score snapshot. Do not recompute DSR, expand
            # startup mirrors/refinements, or consume RNG on exact continuation.
            await self.db.get_population_for_keys(self._resume_population_keys or [])
            self.population=self._resume_population_snapshot
            self._resume_population_snapshot=None
            self._resume_population_keys=None
            return
        exact_membership=self._resume_population_keys is not None
        if exact_membership:
            top = await self.db.get_population_for_keys(self._resume_population_keys)
            self._resume_population_keys = None
        else:
            top = await self.db.get_top_population(config.POPULATION_SIZE)
        if top:
            num_trials = max(2, await self.db.count_trials())
            var_trials = self._estimate_var_trials()
            for row in top:
                (expr, universe, decay, sharpe, turnover, depth, skew,
                 kurtosis, trl, max_corr, alpha_id, _fitness,
                 returns, oos_sharpe, is_qualified) = row
                depth = depth or _ast_depth(expr)
                dsr = self.deflation.calculate_dsr(
                    sharpe, skew or 0.0, kurtosis if kurtosis is not None else 0.0,
                    trl or config.DEFAULT_TRACK_RECORD_LENGTH, num_trials, var_trials,
                )
                # Use the SAME composite fitness (parsimony + IS-OOS + originality
                # shaping) as the live path; the persisted returns/oos_sharpe make
                # the shape penalty reproducible across restarts.
                # Durable score snapshot: do not silently remove the structural/
                # return adjustments applied before _composite_fitness live.
                fitness = _fitness if _fitness is not None else self._composite_fitness(
                    dsr, depth, sharpe, oos_sharpe, expr)
                evidence=parse_checks(await self.db.load_checks(alpha_id))
                self.population.append({
                    "sharpe_2y":evidence.sharpe_2y, "pnl_realization":evidence.pnl_realization,
                    "pyramid_multiplier":evidence.pyramid_multiplier,
                    "failed_checks":",".join(evidence.failed) if evidence.verified else "CHECKS_UNVERIFIABLE",
                    "expression": expr, "universe": universe, "decay": decay,
                    "sharpe": sharpe, "turnover": turnover, "dsr": dsr, "fitness": fitness,
                    "ast_depth": depth, "skew": skew or 0.0, "kurtosis": kurtosis if kurtosis is not None else 0.0,
                    "track_record_length": trl or config.DEFAULT_TRACK_RECORD_LENGTH,
                    "alpha_id": alpha_id or "", "max_correlation": max_corr,
                    "returns": returns if returns is not None else 0.0,
                    "oos_sharpe": oos_sharpe,
                    "is_qualified": bool(is_qualified and evidence.verified and not evidence.failed),
                })
                self.evaluated_canon.add(f"{expr}|{universe}|{decay}")
            logger.info(f"Resumed population with {len(self.population)} alphas.")
            # Resumed members bypass _evaluate_population, so neither the live
            # sign-flip harvest nor inline refinement ever fires for them. Do both
            # once here: (a) mirror any strongly-NEGATIVE resumed alpha into its
            # equally-strong POSITIVE twin, then (b) hill-climb the top resumed
            # winners (including freshly-created mirrors that landed in the pool).
            if not exact_membership:
                await self._harvest_resumed_negatives()
                await self._refine_resumed_winners()
            return

        if exact_membership:
            return

        # Generation-0 field coverage: lift the seed budget to at least the
        # field count so the breadth-first pass can seed EVERY field (it is
        # otherwise bounded by POPULATION_SIZE, which can be far smaller than a
        # dataset-scoped catalog -- e.g. 200 < 371). Every seed is simulated at
        # gen 0, so all fields are actually tested; NSGA-II then truncates the
        # survivors back to POPULATION_SIZE for gen 1.
        seed_count = config.POPULATION_SIZE
        if getattr(config, "SEED_GEN0_COVER_ALL_FIELDS", True):
            seed_count = max(seed_count, len(config.DATA_DICTIONARY))
        seeds = await self.llm.generate_seeds(seed_count, experience=self.experience, avoid_motifs=self._avoid_motifs)
        if not seeds:
            seeds = [self.llm.fill_template(t) for t in config.QUANT_TEMPLATES]
        candidates = [{"expression": s, "universe": config.PRIMARY_UNIVERSE,
                       "decay": self._seed_decay(s), "origin": "seed",
                       "mutation_type": "llm_seed"} for s in seeds]
        await self._evaluate_population(candidates, allow_grid=False)
        logger.info(f"Seeded initial population with {len(self.population)} alphas.")

    async def run(self, generations=None):
        await self.initialize()
        generations = generations or config.GENERATIONS
        if not self.population:
            await self._bootstrap_population()

        # Resume at the checkpointed generation after a logout/restart.
        start_gen = min(self.generation, generations)
        for gen in range(start_gen, generations):
            self.generation = gen
            self.population = await self._select_generation_survivors()
            if not self.population:
                logger.warning("Population collapsed to empty; re-seeding.")
                await self._bootstrap_population()
                continue

            best = self.population[0]
            logger.info(f"Gen {gen}: pop={len(self.population)} best_fitness={best['fitness']:.4f} "
                        f"best_sharpe={best['sharpe']:.3f} submissions={self.submission_count}")

            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))

            # Mid-generation resume: if a checkpoint saved THIS generation's
            # offspring batch (an interrupted run), replay the exact same list
            # instead of regenerating a fresh one. The result_cache/
            # evaluated_canon dedup then skips every offspring already simulated
            # before the restart, so only the UNFINISHED offspring of this
            # generation are re-run -- turning a mid-gen restart from "redo the
            # whole generation" into "finish the batch".
            resumed_offspring = None
            if (self._resume_offspring is not None
                    and self._resume_generation == gen):
                resumed_offspring = self._resume_offspring
                self._recover_pending_keys={f'{c["expression"]}|{c["universe"]}|{c["decay"]}' for c in resumed_offspring}
                self._resume_offspring = None
                self._resume_generation = None
                logger.info(
                    f"Gen {gen}: replaying {len(resumed_offspring)} checkpointed "
                    f"offspring to finish an interrupted generation.")

            if resumed_offspring is not None:
                offspring = resumed_offspring
            else:
                offspring = []

                if gen > 0 and gen % config.EXPERIENCE_RESEED_INTERVAL == 0:
                    seeds = await self.llm.generate_seeds(config.EXPERIENCE_RESEED_COUNT, experience=self.experience, avoid_motifs=self._avoid_motifs)
                    offspring.extend({"expression": s, "universe": config.PRIMARY_UNIVERSE,
                                      "decay": self._seed_decay(s), "origin": "reseed",
                                      "mutation_type": "llm_reseed"} for s in seeds)

                target = max(1, config.POPULATION_SIZE - elite_count)
                guard = 0
                while len(offspring) < target and guard < target * 8:
                    guard += 1
                    parents = self._select_parents()
                    if not parents:
                        break
                    p1, p2 = parents
                    child = self.genetic.crossover(p1["expression"], p2["expression"])
                    mtype = "crossover"
                    if random.random() < config.MUTATION_RATE:
                        child = self.genetic.mutate(child)
                        mtype = "crossover+mutation"
                    offspring.append({"expression": child,
                                      "universe": config.PRIMARY_UNIVERSE,
                                      "decay": self._seed_decay(child),
                                      "origin": "ga",
                                      "parent_id": p1.get("alpha_id") or None,
                                      "mutation_type": mtype})

                # Persist this generation's offspring batch BEFORE evaluating it,
                # so an interrupted run resumes by finishing exactly this batch
                # (dedup skips the already-simulated members) rather than redoing
                # the whole generation. The end-of-generation checkpoint below
                # clears the pending block once this generation completes.
                self._save_checkpoint(pending_offspring=offspring)

            # Elites are carried over implicitly: they stay in self.population and
            # are NEVER re-simulated. Only genuinely new offspring are evaluated.
            await self._evaluate_population(offspring, allow_grid=True)
            self._recover_pending_keys.clear()
            self.population = await self._select_generation_survivors()
            self._trim_state()
            self._save_checkpoint()

        logger.info("Factory run complete.")


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    factory = AlphaFactory()
    try:
        await factory.run()
    finally:
        await factory.shutdown()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
