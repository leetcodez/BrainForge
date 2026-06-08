import ast
import asyncio
import copy
import json
import logging
import math
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine
from oos_deflation import OOSDeflationEngine
from llm_seed_generator import LLMSeedGenerator
from syntax_validator import SyntaxValidator

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
    drawdown: float = 0.0  # IS max drawdown as a fraction (BRAIN 'is.drawdown')
    margin: float = 0.0    # IS margin / $ traded (BRAIN 'is.margin'); can be < 0
    track_record_length: int = config.DEFAULT_TRACK_RECORD_LENGTH
    oos_sharpe: float | None = None
    # Comma-joined names of BRAIN is.checks that FAILED (concentration, sub-
    # universe Sharpe, turnover floor, ...). Empty == BRAIN-clean / no checks.
    failed_checks: str = ""
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
        # Over-used winner motifs to avoid (set by the factory each generation).
        self.avoid_motifs = set()

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

    def mutate(self, expression):
        for _ in range(4):
            op = random.choice(self._mutation_ops)
            try:
                candidate = op(expression)
            except Exception:
                candidate = None
            if candidate and candidate != expression:
                ok, canonical = SyntaxValidator.parse_and_validate(candidate)
                if ok and not SyntaxValidator.is_tautology(canonical):
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
        self.result_cache = {}
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

        self.sim_semaphore = None
        self._state_lock = asyncio.Lock()
        self._active_tasks = set()

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _safe_float(value, default):
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
        """Log a portfolio-level overfitting diagnostic (approx PBO, Upgrade #6)."""
        if not config.PBO_DIAGNOSTIC_ENABLED:
            return
        pairs = [(rec.get("sharpe"), rec.get("oos_sharpe")) for rec in self.population
                 if rec.get("oos_sharpe") is not None]
        if len(pairs) >= 4:
            pbo = self.deflation.estimate_pbo(pairs)
            logger.info(
                f"Portfolio overfitting diagnostic (approx PBO) = {pbo:.2f} "
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

    # --- lifecycle -----------------------------------------------------------
    async def initialize(self):
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
    def _save_checkpoint(self):
        """Persist run-level progress (next generation index + counters) so a
        restart after a logout resumes the cadence instead of replaying the loop
        from zero. The population itself is already checkpointed row-by-row in
        the database during evaluation."""
        try:
            Path(config.CHECKPOINT_PATH).write_text(json.dumps({
                "generation": self.generation + 1,
                "submission_count": self.submission_count,
                "timestamp": time.time(),
            }), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write checkpoint: {e}")

    def _restore_checkpoint(self):
        path = Path(config.CHECKPOINT_PATH)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.generation = int(data.get("generation", 0))
        self.submission_count = int(data.get("submission_count", 0))
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
            resp = await self.network.request("POST", "/simulations", json=payload)
            self.submission_count += 1
            if resp["status_code"] not in (200, 201):
                logger.info(f"Simulation rejected (HTTP {resp['status_code']}).")
                self.result_cache[cache_key] = result
                return result
            poll_url = resp.get("location")
            body = resp.get("json")
            if not poll_url and isinstance(body, dict):
                poll_url = body.get("location") or body.get("url")
            if not poll_url:
                logger.warning("Simulation accepted but no poll URL returned.")
                self.result_cache[cache_key] = result
                return result

            poll_endpoint = poll_url.replace(config.WQ_BASE_URL, "")
            loop = asyncio.get_event_loop()
            deadline = loop.time() + config.SIMULATION_POLL_TIMEOUT_SECS
            while loop.time() < deadline:
                await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
                poll = await self.network.request("GET", poll_endpoint)
                pbody = poll.get("json") or {}
                status = str(pbody.get("status", "")).upper()
                if status in ("ERROR", "FAIL", "FAILED"):
                    errored = True
                    break
                if status == "COMPLETE" or pbody.get("alpha"):
                    alpha_id = pbody.get("alpha")
                    break

        if not alpha_id:
            # Cache genuine errors so we don't retry a broken expression, but do
            # NOT cache timeouts (those may succeed on a later, calmer run).
            if errored:
                self.result_cache[cache_key] = result
            return result

        detail = await self.network.request("GET", f"/alphas/{alpha_id}")
        detail_json = detail.get("json") or {}
        metrics = detail_json.get("is") or {}
        result.alpha_id = alpha_id
        result.sharpe = self._safe_float(metrics.get("sharpe"), 0.0)
        result.turnover = self._safe_float(metrics.get("turnover"), 1.0)
        result.returns = self._safe_float(metrics.get("returns"), 0.0)
        result.skew = self._safe_float(metrics.get("skewness"), 0.0)
        result.kurtosis = self._safe_float(metrics.get("kurtosis"), 0.0)
        # Risk gates (C9): BRAIN reports IS max drawdown and margin alongside the
        # headline stats. A missing field defaults to 0.0 -- which PASSES both
        # gates -- so we never reject an alpha merely because a metric was absent.
        result.drawdown = self._safe_float(metrics.get("drawdown"), 0.0)
        result.margin = self._safe_float(metrics.get("margin"), 0.0)
        # BRAIN submittability checks (is.checks): names of any gate BRAIN itself
        # FAILED (concentration, sub-universe Sharpe, turnover floor, ...) -- the
        # failures our own metric thresholds can't see. PENDING submission-time
        # checks (self-correlation) are not failures and are excluded.
        result.failed_checks = self._failed_check_names(metrics)
        trl = metrics.get("longCount") or metrics.get("trackRecordLength")
        result.track_record_length = int(trl) if trl else config.DEFAULT_TRACK_RECORD_LENGTH
        # Out-of-sample Sharpe when the platform reports it (Upgrade #6). Stays
        # None for fresh sims with no OOS window yet, keeping the penalty neutral.
        os_metrics = detail_json.get("os") or {}
        oos_sharpe = os_metrics.get("sharpe")
        result.oos_sharpe = self._safe_float(oos_sharpe, None) if oos_sharpe is not None else None
        result.valid = True
        # Persist the raw result the INSTANT it completes (incremental + crash-
        # safe). A simulation that finished on WorldQuant must survive even if the
        # run is interrupted before this whole generation's gather() returns --
        # otherwise completed sims that already cost quota silently vanish and the
        # DB looks frozen (e.g. stuck at 197). fitness / is_qualified /
        # max_correlation are still unknown here (they need the generation-level
        # batch); the batch save in _evaluate_population re-saves the SAME sharpe
        # with those filled in, and the db_manager upsert's ">=" guard lets that
        # enrichment through while keeping any genuinely better later result.
        try:
            await self.db.save_alpha(
                result.expression, result.universe, result.decay, result.alpha_id,
                self.generation, result.sharpe, result.turnover, None,
                _ast_depth(result.expression), result.skew, result.kurtosis,
                result.track_record_length, None,
                returns=result.returns, oos_sharpe=result.oos_sharpe,
                is_qualified=0, failed_checks=result.failed_checks,
            )
        except Exception as e:
            logger.warning(f"Could not persist raw simulation result: {e}")
        self.result_cache[cache_key] = result
        return result

    # --- risk gates (C9) -----------------------------------------------------
    def _passes_risk_gates(self, r) -> bool:
        """True unless an alpha trips a hard risk gate BRAIN would reject on:
        excessive IS max drawdown or non-positive margin. Both thresholds are
        config knobs; a None threshold (or DRAWDOWN_MARGIN_GATE_ENABLED=False)
        disables that check, and a missing metric defaults to 0.0 so it passes."""
        if not getattr(config, "DRAWDOWN_MARGIN_GATE_ENABLED", True):
            return True
        max_dd = getattr(config, "MAX_DRAWDOWN", None)
        if max_dd is not None and abs(r.drawdown) > max_dd:
            return False
        min_margin = getattr(config, "MIN_MARGIN", None)
        if min_margin is not None and r.margin < min_margin:
            return False
        return True

    def _risk_fail_reason(self, r) -> str:
        max_dd = getattr(config, "MAX_DRAWDOWN", None)
        if max_dd is not None and abs(r.drawdown) > max_dd:
            return f"high_drawdown ({abs(r.drawdown):.2f} > {max_dd})"
        min_margin = getattr(config, "MIN_MARGIN", None)
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
        '' when no checks are present (gate then fails OPEN)."""
        checks = (metrics or {}).get("checks")
        if not isinstance(checks, list):
            return ""
        failed = []
        for c in checks:
            if not isinstance(c, dict):
                continue
            if str(c.get("result", "")).upper() in ("FAIL", "ERROR"):
                name = str(c.get("name") or c.get("type") or "").strip().upper()
                if name:
                    failed.append(name)
        return ",".join(dict.fromkeys(failed))

    def _passes_checks_gate(self, r) -> bool:
        """True unless BRAIN's own is.checks flagged a blocking FAIL. Fails OPEN
        when the platform returned no checks (missing data never blocks) and when
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
            return 0.0
        attempts = max(1, getattr(config, "CORRELATION_CHECK_ATTEMPTS", 3))
        for attempt in range(attempts):
            try:
                resp = await self.network.request("GET", f"/alphas/{alpha_id}/correlations/self")
                data = resp.get("json")
                records = []
                if isinstance(data, dict):
                    records = data.get("records") or data.get("results") or []
                elif isinstance(data, list):
                    records = data
                values = []
                for row in records:
                    if isinstance(row, dict):
                        v = row.get("correlation", row.get("value", row.get("max")))
                    elif isinstance(row, (list, tuple)) and row:
                        v = row[-1]
                    else:
                        v = row
                    if isinstance(v, (int, float)) and math.isfinite(v):
                        values.append(abs(float(v)))
                return max(values) if values else 0.0
            except Exception as e:
                logger.error(
                    f"Correlation check failed for {alpha_id} "
                    f"(attempt {attempt + 1}/{attempts}): {e}")
                if attempt + 1 < attempts:
                    await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
        # Every attempt failed -> fail CLOSED (treat as fully self-correlated).
        return 1.0

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
            if key in self.evaluated_canon:
                continue
            self.evaluated_canon.add(key)
            prepared.append((canonical, universe, decay))

        filtered = []
        for canonical, universe, decay in prepared:
            # Sign-flip ("mirror") candidates intentionally share almost their
            # entire AST with the negative-Sharpe loser they were derived from,
            # so the near-duplicate-loser guard would wrongly reject them. Skip
            # it for those (the expression|universe|decay dedup above still
            # applies, so nothing is ever double-simulated).
            if not skip_loser_filter and await self._is_near_duplicate_loser(canonical):
                continue
            filtered.append((canonical, universe, decay))
        if not filtered:
            return []

        tasks = [asyncio.create_task(self._simulate_alpha(c, u, d)) for c, u, d in filtered]
        self._active_tasks.update(tasks)
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                self._active_tasks.discard(t)

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
        num_trials = max(2, await self.db.count_trials() + len(valid))
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
        corr_values = await asyncio.gather(
            *[self._check_correlation(prelim[i][0].alpha_id) for i in qual_indices]
        )
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
            }
            promoted = bool(qualifies and (max_corr is None or max_corr <= config.MAX_SELF_CORRELATION))
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
                await self.db.save_alpha(
                    rec["expression"], rec["universe"], rec["decay"], rec["alpha_id"],
                    self.generation, rec["sharpe"], rec["turnover"], rec["fitness"],
                    rec["ast_depth"], rec["skew"], rec["kurtosis"],
                    rec["track_record_length"], rec["max_correlation"],
                    returns=rec.get("returns", 0.0), oos_sharpe=rec.get("oos_sharpe"),
                    is_qualified=1 if rec.get("is_qualified") else 0,
                    failed_checks=rec.get("failed_checks", ""),
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
                                      "decay": rec["decay"], "_mirror_sharpe": mirror_sharpe})
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
        return {"sharpe": e_sharpe, "turnover": e_turnover, "correlation": e_corr}

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
            cands.append({"expression": expr, "universe": uni, "decay": rec["decay"]})
        return cands

    # Tier 2: expression windows -- nudge each lookback to its nearest smaller
    # and larger allowed value. Adds limited degrees of freedom, so it is gated
    # behind a settings plateau.
    def _neighbors_windows(self, rec):
        expr = rec["expression"]
        try:
            tree = ast.parse(expr, mode="eval")
        except Exception:
            return []
        consts = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
        pool = sorted(set(_SHORT_LOOKBACKS + _LONG_LOOKBACKS))
        cands = []
        for idx in range(min(len(consts), 4)):
            current = consts[idx].value
            smaller = [p for p in pool if p < current]
            larger = [p for p in pool if p > current]
            new_vals = ([max(smaller)] if smaller else []) + ([min(larger)] if larger else [])
            for new_val in new_vals:
                variant = self._replace_nth_int(expr, idx, new_val)
                if variant:
                    cands.append({"expression": variant, "universe": rec["universe"], "decay": rec["decay"]})
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
        objs = [(r.get("fitness", float("-inf")), max(r.get("turnover", 1.0), turnover_floor)) for r in population]

        def dominates(i, j):
            fi, ti = objs[i]
            fj, tj = objs[j]
            return (fi >= fj and ti <= tj) and (fi > fj or ti < tj)

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
            for m in range(2):
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
                              "decay": rec["decay"], "_mirror_sharpe": mirror_sharpe})
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
                fitness = self._composite_fitness(dsr, depth, sharpe, oos_sharpe, expr)
                self.population.append({
                    "expression": expr, "universe": universe, "decay": decay,
                    "sharpe": sharpe, "turnover": turnover, "dsr": dsr, "fitness": fitness,
                    "ast_depth": depth, "skew": skew or 0.0, "kurtosis": kurtosis if kurtosis is not None else 0.0,
                    "track_record_length": trl or config.DEFAULT_TRACK_RECORD_LENGTH,
                    "alpha_id": alpha_id or "", "max_correlation": max_corr,
                    "returns": returns if returns is not None else 0.0,
                    "oos_sharpe": oos_sharpe,
                    "is_qualified": bool(is_qualified),
                })
                self.evaluated_canon.add(f"{expr}|{universe}|{decay}")
            logger.info(f"Resumed population with {len(self.population)} alphas.")
            # Resumed members bypass _evaluate_population, so neither the live
            # sign-flip harvest nor inline refinement ever fires for them. Do both
            # once here: (a) mirror any strongly-NEGATIVE resumed alpha into its
            # equally-strong POSITIVE twin, then (b) hill-climb the top resumed
            # winners (including freshly-created mirrors that landed in the pool).
            await self._harvest_resumed_negatives()
            await self._refine_resumed_winners()
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
                       "decay": self._seed_decay(s)} for s in seeds]
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
            self.population = self._enforce_skeleton_diversity(self._nsga_ii_sort(self.population))[: config.POPULATION_SIZE]
            if not self.population:
                logger.warning("Population collapsed to empty; re-seeding.")
                await self._bootstrap_population()
                continue

            best = self.population[0]
            logger.info(f"Gen {gen}: pop={len(self.population)} best_fitness={best['fitness']:.4f} "
                        f"best_sharpe={best['sharpe']:.3f} submissions={self.submission_count}")

            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
            offspring = []

            if gen > 0 and gen % config.EXPERIENCE_RESEED_INTERVAL == 0:
                seeds = await self.llm.generate_seeds(config.EXPERIENCE_RESEED_COUNT, experience=self.experience, avoid_motifs=self._avoid_motifs)
                offspring.extend({"expression": s, "universe": config.PRIMARY_UNIVERSE,
                                  "decay": self._seed_decay(s)} for s in seeds)

            target = max(1, config.POPULATION_SIZE - elite_count)
            guard = 0
            while len(offspring) < target and guard < target * 8:
                guard += 1
                parents = self._select_parents()
                if not parents:
                    break
                p1, p2 = parents
                child = self.genetic.crossover(p1["expression"], p2["expression"])
                if random.random() < config.MUTATION_RATE:
                    child = self.genetic.mutate(child)
                offspring.append({"expression": child,
                                  "universe": config.PRIMARY_UNIVERSE,
                                  "decay": self._seed_decay(child)})

            # Elites are carried over implicitly: they stay in self.population and
            # are NEVER re-simulated. Only genuinely new offspring are evaluated.
            await self._evaluate_population(offspring, allow_grid=True)
            self.population = self._enforce_skeleton_diversity(self._nsga_ii_sort(self.population))[: config.POPULATION_SIZE]
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