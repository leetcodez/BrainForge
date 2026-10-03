"""Read-only post-mortem / diagnostics for a BrainForge run database.

Mines alpha_population (+ AST structure) and alpha_pnl and reports, quantitatively,
what went wrong in a run: monoculture, operator under-use, behavioral correlation
(Effective Number of Bets), overfitting (Deflated Sharpe, CSCV/PBO) and GA search
health. Mirrors decorrelation_selector.py / backfill_pnl.py: a standalone CLI that
SUBMITS NOTHING, MUTATES NOTHING, and never imports the orchestrator.

HARD read-only guarantee
------------------------
The run DB is opened with sqlite ``mode=ro`` so the OS itself rejects any write.
The only thing this tool writes is its OWN cross-run history DB (a SEPARATE file,
default diagnostics_history.db) plus the report/JSON/plots in --out-dir. It can
NEVER touch brain_memory*.db.

Reuse, don't reinvent (per the design spec)
-------------------------------------------
* decorrelation_selector._daily_returns  -> gap-correct daily differencing
* oos_deflation.OOSDeflationEngine        -> Deflated Sharpe primitive
* syntax_validator.SyntaxValidator        -> AST motifs / canonical skeletons
* config.field_family / FIELD_GROUPS      -> field-family rollups (selector agrees by construction)

Usage
-----
    python run_diagnostics.py --db brain_memory.earnings4_run2.db --plots
    python run_diagnostics.py --db <run.db> --scope qualified --out-dir diag_out

Dependencies: numpy (hard), scipy.stats (already a project dep via oos_deflation),
matplotlib (optional; plots are skipped if unavailable).
"""
import argparse
import ast
import datetime
import itertools
import json
import math
import os
import random
import sqlite3
from collections import Counter, defaultdict

import numpy as np

import config
from decorrelation_selector import _daily_returns
from oos_deflation import OOSDeflationEngine
from syntax_validator import SyntaxValidator

try:
    import scipy.stats as ss
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover - scipy is a project dep, but stay defensive
    _HAVE_SCIPY = False


# ---------------------------------------------------------------------------
# Tunables (all overridable from the CLI). Conservative so behavioral numbers
# never get computed on too-thin data and quietly lie.
# ---------------------------------------------------------------------------
MIN_BEHAVIORAL_ALPHAS = 3       # need at least this many PnL series for ENB/clusters
MIN_BEHAVIORAL_DAYS = 60        # minimum overlapping trading days in the matrix
MIN_PNL_COVERAGE = 0.30         # fraction of the scope that must have stored PnL
CSCV_BLOCKS = 10                # S in CSCV (must be even); auto-reduced if T is short
CSCV_MAX_COMBOS = 2000          # cap combinatorial splits (sample beyond this)
CLUSTER_THRESHOLDS = (0.5, 0.7) # |corr| connectivity thresholds for cluster counting
Z_95 = 1.6448536269514722       # one-sided 95% normal quantile (norm.ppf(0.95))
DSR_CONFIDENCE = 0.95           # a DSR "survivor" must clear the hurdle at >=95% confidence


# ===========================================================================
# 0. Read-only data access
# ===========================================================================
def open_readonly(db_path):
    """Open the run DB strictly read-only. Raises if the file is missing rather
    than silently creating an empty DB (the default sqlite3.connect footgun)."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"run DB not found: {db_path}")
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def load_population(conn, scope="all"):
    """Return a list of dict rows from alpha_population.

    scope: 'all'       -> every simulated row (sharpe IS NOT NULL)
           'qualified' -> is_qualified = 1 only

    Lineage columns (parent_id / mutation_type / origin) are selected ONLY when
    the run DB actually has them, so this stays compatible with older runs that
    pre-date the lineage instrumentation (their Module-4 lineage metrics simply
    report NOT COMPUTABLE)."""
    cols = ["id", "expression", "universe", "decay", "alpha_id", "generation",
            "sharpe", "turnover", "fitness", "ast_depth", "skew", "kurtosis",
            "track_record_length", "max_correlation", "returns", "oos_sharpe",
            "is_qualified"]
    present = _table_columns(conn, "alpha_population")
    for opt in ("parent_id", "mutation_type", "origin"):
        if opt in present:
            cols.append(opt)
    where = "sharpe IS NOT NULL"
    if scope == "qualified":
        where += " AND is_qualified = 1"
    cur = conn.execute(
        f"SELECT {', '.join(cols)} FROM alpha_population WHERE {where} ORDER BY id ASC"
    )
    return [dict(r) for r in cur.fetchall()]


def load_pnl_returns(conn, alpha_ids):
    """alpha_id -> {date: one-period return} using the SAME gap-correct
    differencing the submission selector uses, so diagnostics and selector
    agree by construction. Skips ids with no stored series."""
    out = {}
    for aid in alpha_ids:
        if not aid or aid == "MANUAL_SEED":
            continue
        rows = conn.execute(
            "SELECT date, pnl FROM alpha_pnl WHERE alpha_id = ? ORDER BY date ASC",
            (aid,),
        ).fetchall()
        if not rows:
            continue
        ret = _daily_returns([(r[0], r[1]) for r in rows])
        if ret:
            out[aid] = ret
    return out


# ===========================================================================
# 1. AST helpers (structural layer)
# ===========================================================================
def _safe_tree(expr):
    try:
        return ast.parse(expr, mode="eval")
    except Exception:
        return None


def _operator_calls(tree):
    """Lower-cased operator names called in the expression (with repeats)."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            out.append(node.func.id.lower())
    return out


def _depth_and_nodes(tree):
    def depth(node):
        return 1 + max((depth(c) for c in ast.iter_child_nodes(node)), default=0)
    nodes = sum(1 for _ in ast.walk(tree))
    return depth(tree), nodes


def _outer_call_name(tree):
    body = tree.body if isinstance(tree, ast.Expression) else tree
    # unwrap a leading unary minus, e.g. -group_neutralize(...)
    while isinstance(body, ast.UnaryOp):
        body = body.operand
    if isinstance(body, ast.Call) and isinstance(body.func, ast.Name):
        return body.func.id.lower(), body
    return None, None


_NEUT_GROUP_OPS = {"group_neutralize", "group_zscore", "group_rank", "group_scale",
                   "group_mean", "group_vector_neut"}
_MARKET_NEUT_OPS = {"normalize", "zscore", "vector_neut"}


def _neutralization(tree):
    """(style, group_key). style is the outer neutralizer op (or 'none'); group_key
    is the SUBINDUSTRY/INDUSTRY/SECTOR/MARKET token when present."""
    name, call = _outer_call_name(tree)
    if name is None:
        return "none", None
    if name in _NEUT_GROUP_OPS:
        group_key = None
        if call.args:
            last = call.args[-1]
            if isinstance(last, ast.Name) and last.id.upper() in set(config.NEUTRALIZATIONS):
                group_key = last.id.upper()
        return name, group_key
    if name in _MARKET_NEUT_OPS:
        return name, "MARKET"
    return "none", None


def _skeleton(expr):
    """Whole-expression structural skeleton: fields -> '_', constants -> '_',
    neutralization group token -> '_'. So group_neutralize(rank(iv_a), INDUSTRY)
    and group_neutralize(rank(iv_b), SECTOR) collapse to the same skeleton."""
    tree = _safe_tree(expr)
    if tree is None:
        return None
    ops = {o.lower() for o in config.ALLOWED_OPERATORS}

    class _Abstract(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id.lower() in ops:
                return node  # keep operator names
            return ast.copy_location(ast.Name(id="_", ctx=ast.Load()), node)

        def visit_Constant(self, node):
            return ast.copy_location(ast.Constant(value="_"), node)

    try:
        abstracted = _Abstract().visit(tree)
        ast.fix_missing_locations(abstracted)
        return ast.unparse(abstracted)
    except Exception:
        return None


def _field_tokens(tree):
    """Leaf identifiers that are neither operators nor neutralization keys ->
    treated as data fields."""
    ops = {o.lower() for o in config.ALLOWED_OPERATORS}
    neut = set(config.NEUTRALIZATIONS)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            nid = node.id
            if nid.lower() in ops or nid.upper() in neut:
                continue
            out.append(nid)
    return out


def _hhi(counter):
    """Herfindahl index and effective count (1/HHI) over a Counter of shares."""
    total = sum(counter.values())
    if total <= 0:
        return None, None
    hhi = sum((v / total) ** 2 for v in counter.values())
    return hhi, (1.0 / hhi if hhi > 0 else None)


def _norm_entropy(counter, support=None):
    """Shannon entropy normalized to [0,1]. support = size of the universe to
    normalize against (defaults to observed categories). Using the FULL operator
    universe makes unused operators drag entropy down (honest monoculture read)."""
    total = sum(counter.values())
    if total <= 0:
        return None
    h = 0.0
    for v in counter.values():
        if v > 0:
            p = v / total
            h -= p * math.log(p)
    n = support if support and support > 1 else len(counter)
    if not n or n <= 1:
        return 0.0
    return h / math.log(n)


def module1_structural(pop):
    """Operator coverage/entropy, neutralization distribution, field/family HHI,
    archetype distribution, complexity, AST clone similarity. No PnL needed."""
    op_counter = Counter()
    alphas_using_op = Counter()       # how many alphas use each op at least once
    neut_style = Counter()
    neut_group = Counter()
    field_counter = Counter()
    family_counter = Counter()
    skeleton_counter = Counter()
    depths, nodes = [], []
    turnovers, decays = [], []
    op_bigrams = Counter()            # parent_op -> child_op co-occurrence
    n_parsed = 0

    for row in pop:
        expr = row["expression"] or ""
        if row.get("turnover") is not None:
            turnovers.append(row["turnover"])
        if row.get("decay") is not None:
            decays.append(row["decay"])
        tree = _safe_tree(expr)
        if tree is None:
            continue
        n_parsed += 1
        ops_here = _operator_calls(tree)
        op_counter.update(ops_here)
        for op in set(ops_here):
            alphas_using_op[op] += 1
        style, gkey = _neutralization(tree)
        neut_style[style] += 1
        if gkey:
            neut_group[gkey] += 1
        for fld in _field_tokens(tree):
            field_counter[fld] += 1
            fam = config.field_family(fld) or "unknown"
            family_counter[fam] += 1
        sk = _skeleton(expr)
        if sk:
            skeleton_counter[sk] += 1
        d, nd = _depth_and_nodes(tree)
        depths.append(d)
        nodes.append(nd)
        # operator parent->child bigrams
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                pname = node.func.id.lower()
                for child in ast.walk(node):
                    if child is node:
                        continue
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        op_bigrams[(pname, child.func.id.lower())] += 1
                        break

    available_ops = sorted({o.lower() for o in config.ALLOWED_OPERATORS})
    used_ops = set(op_counter)
    zero_usage = [o for o in available_ops if o not in used_ops]
    field_hhi, field_eff = _hhi(field_counter)
    fam_hhi, fam_eff = _hhi(family_counter)

    # AST clone similarity: mean max-motif-Jaccard of a sample of alphas vs the
    # rest (full pairwise is O(n^2); sample to keep it cheap and indicative).
    exprs = [r["expression"] for r in pop if r.get("expression")]
    clone_sim = _sampled_clone_similarity(exprs)

    top_neut = neut_style.most_common(1)[0] if neut_style else (None, 0)
    return {
        "n_alphas": len(pop),
        "n_parsed": n_parsed,
        "operator_usage": dict(op_counter.most_common()),
        "operator_coverage": (len(used_ops) / len(available_ops)) if available_ops else None,
        "operators_available": len(available_ops),
        "operators_used": len(used_ops),
        "operators_zero_usage": zero_usage,
        "operator_entropy_norm": _norm_entropy(op_counter, support=len(available_ops)),
        "neutralization_style": dict(neut_style.most_common()),
        "neutralization_group_key": dict(neut_group.most_common()),
        "max_neut_share": (top_neut[1] / n_parsed) if n_parsed else None,
        "field_hhi": field_hhi,
        "effective_field_count": field_eff,
        "field_family_hhi": fam_hhi,
        "effective_family_count": fam_eff,
        "family_distribution": dict(family_counter.most_common()),
        "top_fields": dict(field_counter.most_common(15)),
        "archetype_distribution": dict(skeleton_counter.most_common(12)),
        "n_distinct_skeletons": len(skeleton_counter),
        "max_archetype_share": (skeleton_counter.most_common(1)[0][1] / n_parsed) if (n_parsed and skeleton_counter) else None,
        "depth": _dist(depths),
        "nodes": _dist(nodes),
        "turnover": _dist(turnovers),
        "decay": _dist(decays),
        "top_operator_bigrams": {f"{a}>{b}": c for (a, b), c in op_bigrams.most_common(12)},
        "ast_clone_similarity_mean": clone_sim,
    }


def _sampled_clone_similarity(exprs, sample=120, seed=0):
    uniq = list(dict.fromkeys(e for e in exprs if e))
    if len(uniq) < 2:
        return None
    rng = random.Random(seed)
    sample_set = uniq if len(uniq) <= sample else rng.sample(uniq, sample)
    sims = []
    for i, e in enumerate(sample_set):
        refs = sample_set[:i] + sample_set[i + 1:]
        try:
            sims.append(SyntaxValidator.motif_similarity(e, refs))
        except Exception:
            continue
    return float(np.mean(sims)) if sims else None


def _dist(values):
    arr = np.array([v for v in values if v is not None], dtype=float)
    if arr.size == 0:
        return None
    return {
        "n": int(arr.size),
        "min": float(np.min(arr)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "p75": float(np.percentile(arr, 75)),
        "max": float(np.max(arr)),
    }


# ===========================================================================
# 2. Behavioral layer (the truth layer): ENB, PC1, clusters
# ===========================================================================
def build_return_matrix(returns_by_alpha, min_days=MIN_BEHAVIORAL_DAYS):
    """Align per-alpha return dicts into a complete-case (T x N) matrix.

    Strategy: drop alphas with < min_days observations, take the date
    INTERSECTION across the survivors, and if that is too thin progressively
    drop the sparsest alphas until the common window clears min_days. Returns
    (dates, alpha_ids, matrix, coverage_fraction). Complete-case keeps the
    correlation honest (no imputation), at the cost of dropping short series --
    which is reported as coverage.
    """
    series = {a: r for a, r in returns_by_alpha.items() if len(r) >= min_days}
    if len(series) < MIN_BEHAVIORAL_ALPHAS:
        return None
    # Greedy: keep dropping the alpha that most shrinks the intersection until
    # the common date window is large enough (or we run out of alphas).
    aids = list(series)
    while aids:
        common = set(series[aids[0]])
        for a in aids[1:]:
            common &= set(series[a])
        if len(common) >= min_days and len(aids) >= MIN_BEHAVIORAL_ALPHAS:
            break
        # Drop the SHORTEST series: it is the one most likely constraining the
        # date intersection. (Comparing each alpha against `common` is useless --
        # every surviving alpha is a superset of the running intersection, so
        # that overlap is identical for all of them and never identifies a
        # genuine outlier.)
        worst = min(aids, key=lambda a: len(series[a]))
        aids.remove(worst)
    if len(aids) < MIN_BEHAVIORAL_ALPHAS:
        return None
    common_dates = sorted(set.intersection(*[set(series[a]) for a in aids]))
    if len(common_dates) < min_days:
        return None
    M = np.array([[series[a][d] for a in aids] for d in common_dates], dtype=float)
    coverage = len(aids) / len(returns_by_alpha)
    return common_dates, aids, M, coverage


def _corr_matrix(M):
    """Pearson correlation across columns of a complete-case T x N matrix, with
    flat (zero-variance) columns dropped, then repaired to the nearest PSD
    matrix (clip negative eigenvalues) so eigen-work is well defined."""
    std = M.std(axis=0)
    keep = std > 0
    M = M[:, keep]
    if M.shape[1] < 2:
        return None, keep
    C = np.corrcoef(M, rowvar=False)
    C = np.nan_to_num(C, nan=0.0)
    # nearest-PSD: clip negative eigenvalues, renormalize diagonal to 1.
    w, V = np.linalg.eigh((C + C.T) / 2.0)
    w = np.clip(w, 0.0, None)
    C = V @ np.diag(w) @ V.T
    d = np.sqrt(np.clip(np.diag(C), 1e-12, None))
    C = C / np.outer(d, d)
    return C, keep


def _enb_from_eigs(eigs):
    eigs = np.clip(np.asarray(eigs, dtype=float), 0.0, None)
    s = eigs.sum()
    if s <= 0:
        return None, None
    p = eigs / s
    p = p[p > 0]
    enb = float(np.exp(-np.sum(p * np.log(p))))
    pc1 = float(eigs.max() / s)
    return enb, pc1


def _mp_denoise(eigs, q):
    """Constant-residual Marchenko-Pastur denoising (Lopez de Prado): eigenvalues
    below the MP upper edge lambda+ = (1+sqrt(q))^2 are noise; replace them with
    their common mean so the trace (total variance) is preserved. Returns the
    denoised eigenvalue spectrum."""
    eigs = np.sort(np.clip(np.asarray(eigs, dtype=float), 0.0, None))[::-1]
    lam_plus = (1.0 + math.sqrt(q)) ** 2 if q > 0 else eigs.max()
    noise = eigs < lam_plus
    if noise.sum() >= 1 and (~noise).sum() >= 1:
        eigs = eigs.copy()
        eigs[noise] = eigs[noise].mean()
    return eigs, lam_plus


def _cluster_count(C, threshold):
    """Connected-components cluster count: alphas linked when |corr| > threshold
    (union-find). No sklearn/scipy dependency."""
    n = C.shape[0]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    A = np.abs(C)
    for i in range(n):
        for j in range(i + 1, n):
            if A[i, j] > threshold:
                union(i, j)
    return len({find(i) for i in range(n)})


def module2_behavioral(returns_by_alpha, pop_by_id, scope_label):
    built = build_return_matrix(returns_by_alpha)
    if built is None:
        return {"available": False, "reason": "insufficient PnL coverage/overlap",
                "scope": scope_label, "n_with_pnl": len(returns_by_alpha)}
    dates, aids, M, coverage = built
    C, keep = _corr_matrix(M)
    if C is None:
        return {"available": False, "reason": "degenerate correlation matrix",
                "scope": scope_label}
    kept_aids = [a for a, k in zip(aids, keep) if k]
    eigs = np.linalg.eigvalsh(C)
    enb_raw, pc1 = _enb_from_eigs(eigs)
    N, T = C.shape[0], M.shape[0]
    q = N / T if T > 0 else 1.0
    eigs_dn, lam_plus = _mp_denoise(eigs, q)
    enb_dn, pc1_dn = _enb_from_eigs(eigs_dn)
    iu = np.triu_indices_from(C, k=1)
    mean_abs_corr = float(np.mean(np.abs(C[iu]))) if iu[0].size else None
    clusters = {str(t): _cluster_count(C, t) for t in CLUSTER_THRESHOLDS}
    reps = _cluster_representatives(C, kept_aids, pop_by_id, CLUSTER_THRESHOLDS[-1])
    return {
        "available": True,
        "scope": scope_label,
        "n_alphas_in_matrix": N,
        "n_days": T,
        "coverage": coverage,
        "q_ratio_N_over_T": q,
        "enb_raw": enb_raw,
        "enb_denoised": enb_dn,
        "mp_lambda_plus": lam_plus,
        "pc1_share_raw": pc1,
        "pc1_share_denoised": pc1_dn,
        "mean_abs_corr": mean_abs_corr,
        "cluster_count": clusters,
        "cluster_representatives": reps,
    }


def _cluster_representatives(C, aids, pop_by_id, threshold):
    """Name each behavioral cluster (|corr|>threshold components) by its
    highest-fitness member and that member's archetype skeleton."""
    n = C.shape[0]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    A = np.abs(C)
    for i in range(n):
        for j in range(i + 1, n):
            if A[i, j] > threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    reps = []
    for members in sorted(groups.values(), key=len, reverse=True):
        best = None
        for idx in members:
            row = pop_by_id.get(aids[idx])
            if row is None:
                continue
            fit = row.get("fitness")
            fit = fit if fit is not None else float("-inf")
            if best is None or fit > best[0]:
                best = (fit, row)
        if best is None:
            continue
        row = best[1]
        reps.append({
            "size": len(members),
            "alpha_id": row.get("alpha_id"),
            "fitness": row.get("fitness"),
            "sharpe": row.get("sharpe"),
            "archetype": _skeleton(row.get("expression") or ""),
            "expression": row.get("expression"),
        })
        if len(reps) >= 12:
            break
    return reps


# ===========================================================================
# 3. Statistical validity: Deflated Sharpe, CSCV/PBO, MinTRL
# ===========================================================================
def _expected_max_sharpe_uncapped(num_trials, var_trials):
    """Local copy of oos_deflation's expected-max-Sharpe WITHOUT the
    DEFLATION_MAX_TRIALS cap, so we can show DSR under the TRUE trial count
    (the spec's whole point). We do NOT mutate config; the production engine
    keeps its capped behaviour."""
    if num_trials < 2 or var_trials <= 0 or not _HAVE_SCIPY:
        return 0.0
    gamma = 0.5772156649015329
    sigma = math.sqrt(var_trials)
    z1 = ss.norm.ppf(1.0 - 1.0 / num_trials)
    z2 = ss.norm.ppf(1.0 - 1.0 / (num_trials * math.e))
    return sigma * ((1.0 - gamma) * z1 + gamma * z2)


def module3_statistical(pop, n_trials_true):
    """DSR per alpha under capped vs true N; CSCV/PBO handled separately (needs
    the return matrix). Also MinTRL for the top alphas and the IS-OOS gap flag."""
    engine = OOSDeflationEngine()
    sqrt_p = math.sqrt(config.PERIODS_IN_YEAR)
    # per-period trial Sharpe variance across the population (the multiple-
    # testing dispersion the DSR needs).
    pp_sharpes = [r["sharpe"] / sqrt_p for r in pop if r.get("sharpe") is not None]
    var_trials = float(np.var(pp_sharpes)) if len(pp_sharpes) > 1 else 0.0
    cap = getattr(config, "DEFLATION_MAX_TRIALS", 0)
    n_capped = min(n_trials_true, cap) if (cap and cap > 1) else n_trials_true

    # Two multiple-testing hurdles (expected-max Sharpe over the trials):
    #   * capped -> reuse the PRODUCTION engine, which caps at DEFLATION_MAX_TRIALS
    #   * true-N -> local uncapped copy at the real trial count.
    # A "survivor" is an alpha whose deflation PROBABILITY P(SR > hurdle) clears
    # DSR_CONFIDENCE. (The old code tested calculate_dsr() > 0, but that product
    # is sharpe * probability and the probability is never exactly 0 -- so it
    # merely counted positive-Sharpe alphas and was IDENTICAL for both hurdles,
    # which defeated the whole capped-vs-true comparison.)
    sr0_capped = engine._expected_max_sharpe(n_trials_true, var_trials)
    sr0_true = _expected_max_sharpe_uncapped(n_trials_true, var_trials)

    survive_capped = survive_true = 0
    scored = 0
    dsr_true_top = []
    for r in pop:
        s = r.get("sharpe")
        if s is None:
            continue
        skew = r.get("skew") or 0.0
        kurt = r.get("kurtosis")
        kurt = kurt if kurt is not None else (0.0 if config.KURTOSIS_IS_EXCESS else 3.0)
        trl = r.get("track_record_length") or config.DEFAULT_TRACK_RECORD_LENGTH
        scored += 1
        p_capped = _dsr_probability(s, skew, kurt, trl, sr0_capped, sqrt_p)
        p_true = _dsr_probability(s, skew, kurt, trl, sr0_true, sqrt_p)
        if p_capped >= DSR_CONFIDENCE:
            survive_capped += 1
        if p_true >= DSR_CONFIDENCE:
            survive_true += 1
        # Reported deflated Sharpe keeps the engine's definition (sharpe x prob)
        # under the honest true-N hurdle.
        dsr_true_top.append((s * p_true, r))

    dsr_true_top.sort(key=lambda x: x[0], reverse=True)
    top = []
    for dsr_true, r in dsr_true_top[:10]:
        mintrl = _min_trl(r, var_trials, n_trials_true, sqrt_p)
        top.append({
            "alpha_id": r.get("alpha_id"), "sharpe": r.get("sharpe"),
            "fitness": r.get("fitness"), "dsr_true_N": dsr_true,
            "min_trl_years": mintrl,
        })

    oos_present = sum(1 for r in pop if r.get("oos_sharpe") is not None)
    return {
        "n_trials_true": n_trials_true,
        "n_trials_capped": n_capped,
        "var_trials_per_period": var_trials,
        "n_scored": scored,
        "dsr_survivors_capped_N": survive_capped,
        "dsr_survivors_true_N": survive_true,
        "dsr_survival_rate_true_N": (survive_true / scored) if scored else None,
        "top_alphas_by_dsr": top,
        "oos_sharpe_present": oos_present,
        "oos_gap_flag": (oos_present == 0),
    }


def _dsr_probability(sharpe, skew, kurtosis, trl, sr0, sqrt_p):
    """P(true per-period SR > hurdle sr0) under non-normality, mirroring
    oos_deflation.calculate_dsr's per-period variance math EXACTLY (so our
    numbers reconcile with the production engine). Returns a probability in
    [0, 1]; the deflated Sharpe is sharpe * this probability."""
    if sharpe is None or not math.isfinite(sharpe) or not _HAVE_SCIPY:
        return 0.0
    n = max(2, int(trl or config.DEFAULT_TRACK_RECORD_LENGTH))
    sr = sharpe / sqrt_p
    gamma4 = kurtosis + 3.0 if config.KURTOSIS_IS_EXCESS else kurtosis
    sr_var = (1.0 - skew * sr + ((gamma4 - 1.0) / 4.0) * sr * sr) / (n - 1)
    if not math.isfinite(sr_var) or sr_var <= 0:
        return 0.0
    z = (sr - sr0) / math.sqrt(sr_var)
    return float(ss.norm.cdf(z))


def _min_trl(row, var_trials, n_trials, sqrt_p):
    """Minimum Track Record Length (Bailey & Lopez de Prado), in YEARS, for the
    alpha's per-period Sharpe to beat the multiple-testing hurdle at 95%."""
    if not _HAVE_SCIPY:
        return None
    s = row.get("sharpe")
    if s is None:
        return None
    sr = s / sqrt_p
    sr0 = _expected_max_sharpe_uncapped(n_trials, var_trials)
    if sr <= sr0:
        return None  # never clears the hurdle
    skew = row.get("skew") or 0.0
    kurt = row.get("kurtosis")
    kurt = kurt if kurt is not None else (0.0 if config.KURTOSIS_IS_EXCESS else 3.0)
    gamma4 = kurt + 3.0 if config.KURTOSIS_IS_EXCESS else kurt
    var_term = 1.0 - skew * sr + ((gamma4 - 1.0) / 4.0) * sr * sr
    n_periods = 1.0 + var_term * (Z_95 / (sr - sr0)) ** 2
    return float(n_periods / config.PERIODS_IN_YEAR)


def cscv_pbo(M, blocks=CSCV_BLOCKS, max_combos=CSCV_MAX_COMBOS, seed=0):
    """Probability of Backtest Overfitting via Combinatorially Symmetric
    Cross-Validation (Bailey et al.). Split T rows into S blocks; for each
    balanced IS/OOS partition, find the IS-best alpha and record its OOS rank;
    PBO = fraction of partitions where the IS-best lands below the OOS median
    (logit <= 0). Indicative on short single-dataset series."""
    T, N = M.shape
    if N < 4 or T < blocks * 4:
        return {"available": False, "reason": "too few alphas/days for CSCV"}
    if blocks % 2 == 1:
        blocks -= 1
    idx = np.array_split(np.arange(T), blocks)
    half = blocks // 2
    all_combos = list(itertools.combinations(range(blocks), half))
    rng = random.Random(seed)
    if len(all_combos) > max_combos:
        all_combos = rng.sample(all_combos, max_combos)

    def sharpe(sub):
        mu = sub.mean(axis=0)
        sd = sub.std(axis=0, ddof=1)
        sd = np.where(sd > 0, sd, np.nan)
        return mu / sd

    logits = []
    for combo in all_combos:
        is_rows = np.concatenate([idx[b] for b in combo])
        oos_rows = np.concatenate([idx[b] for b in range(blocks) if b not in combo])
        is_s = sharpe(M[is_rows])
        oos_s = sharpe(M[oos_rows])
        if np.all(np.isnan(is_s)):
            continue
        n_star = int(np.nanargmax(is_s))
        oos_valid = oos_s[~np.isnan(oos_s)]
        if oos_valid.size < 2 or math.isnan(oos_s[n_star]):
            continue
        rank = (oos_valid < oos_s[n_star]).sum() / oos_valid.size  # in [0,1]
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1 - rank)))
    if not logits:
        return {"available": False, "reason": "no valid CSCV partitions"}
    logits = np.array(logits)
    return {
        "available": True,
        "pbo": float((logits <= 0).mean()),
        "n_partitions": int(logits.size),
        "blocks": blocks,
        "median_logit": float(np.median(logits)),
    }


# ===========================================================================
# 4. GA / search health
# ===========================================================================
def module4_search(pop, returns_by_alpha):
    """Per-generation diversity collapse, fitness progression, duplicate rate,
    plus HONEST flags for the metrics the current schema cannot support."""
    by_gen = defaultdict(list)
    for r in pop:
        g = r.get("generation")
        if g is None:
            continue
        by_gen[g].append(r)

    per_gen = []
    for g in sorted(by_gen):
        rows = by_gen[g]
        op_counter = Counter()
        fam_counter = Counter()
        sharpes, fits = [], []
        skeletons = Counter()
        for r in rows:
            tree = _safe_tree(r.get("expression") or "")
            if tree is not None:
                op_counter.update(_operator_calls(tree))
                for fld in _field_tokens(tree):
                    fam_counter[config.field_family(fld) or "unknown"] += 1
                sk = _skeleton(r.get("expression") or "")
                if sk:
                    skeletons[sk] += 1
            if r.get("sharpe") is not None:
                sharpes.append(r["sharpe"])
            if r.get("fitness") is not None:
                fits.append(r["fitness"])
        fam_hhi, fam_eff = _hhi(fam_counter)
        win_rate = (sum(1 for s in sharpes if s >= config.MIN_SHARPE) / len(sharpes)) if sharpes else None
        per_gen.append({
            "generation": g,
            "n": len(rows),
            "operator_entropy_norm": _norm_entropy(op_counter, support=len(config.ALLOWED_OPERATORS)),
            "effective_family_count": fam_eff,
            "best_sharpe": max(sharpes) if sharpes else None,
            "median_sharpe": float(np.median(sharpes)) if sharpes else None,
            "best_fitness": max(fits) if fits else None,
            "median_fitness": float(np.median(fits)) if fits else None,
            "winner_base_rate": win_rate,
            "distinct_skeletons": len(skeletons),
        })

    # Fitness lift: best of last generation vs best seed (generation 0).
    lift = None
    if per_gen:
        gen0 = next((p for p in per_gen if p["generation"] == 0), None)
        last = per_gen[-1]
        if gen0 and gen0.get("best_fitness") is not None and last.get("best_fitness") is not None:
            lift = last["best_fitness"] - gen0["best_fitness"]

    # Wasted compute: fraction of expressions that are AST-motif near-duplicates
    # of an earlier one (cheap structural proxy, not return-correlation).
    dup_rate = _duplicate_rate(pop)

    lineage = _lineage_metrics(pop)

    return {
        "generations_present": sorted(by_gen),
        "per_generation": per_gen,
        "best_fitness_lift_vs_seed": lift,
        "structural_duplicate_rate": dup_rate,
        "lineage": lineage,
    }


def _lineage_metrics(pop):
    """Lineage concentration, mutation productivity and reseed/origin survival.

    These require the lineage instrumentation (parent_id / mutation_type /
    origin). When the run pre-dates it, each metric is returned as a
    NOT COMPUTABLE string with the exact one-line schema fix -- the same
    treatment the empty oos_sharpe column gets, never faked.

    NOTE: lineage is 'first-discovery' approximate -- the (expression, universe,
    decay) UNIQUE upsert collapses a re-discovered alpha onto its first row, so
    parent_id reflects the FIRST parent that produced it, not a full genealogy."""
    has_parent = any(r.get("parent_id") for r in pop)
    has_mut = any(r.get("mutation_type") for r in pop)
    has_origin = any(r.get("origin") for r in pop)
    out = {}

    # --- lineage concentration: offspring per parent (HHI / effective count) --
    if has_parent:
        child_counts = Counter(r["parent_id"] for r in pop if r.get("parent_id"))
        hhi, eff = _hhi(child_counts)
        out["lineage_concentration"] = {
            "parents_with_offspring": len(child_counts),
            "offspring_hhi": hhi,
            "effective_parent_count": eff,
            "top_parents": dict(child_counts.most_common(8)),
        }
    else:
        out["lineage_concentration"] = ("NOT COMPUTABLE: no parent_id recorded. Add a parent_id "
                                        "TEXT column (written at offspring creation) to enable it.")

    # --- mutation productivity: fraction of children beating their parent -----
    if has_parent and has_mut:
        fitness_by_alpha = {r["alpha_id"]: r.get("fitness") for r in pop
                            if r.get("alpha_id") and r.get("fitness") is not None}
        by_type = defaultdict(lambda: [0, 0])  # mutation_type -> [beats, total]
        for r in pop:
            pid = r.get("parent_id")
            cf = r.get("fitness")
            if not pid or cf is None or pid not in fitness_by_alpha:
                continue
            mt = r.get("mutation_type") or "unknown"
            by_type[mt][1] += 1
            if cf > fitness_by_alpha[pid]:
                by_type[mt][0] += 1
        out["mutation_productivity"] = {
            mt: {"beats_parent": b, "evaluated": t,
                 "productivity": (b / t) if t else None}
            for mt, (b, t) in sorted(by_type.items(), key=lambda kv: -kv[1][1])
        } or "NOT COMPUTABLE: no child rows carry a resolvable parent fitness yet."
    else:
        out["mutation_productivity"] = ("NOT COMPUTABLE: needs parent_id + mutation_type. Add both "
                                        "(written at offspring creation) to measure which mutations beat their parent.")

    # --- origin / reseed survival: qualified rate by origin -------------------
    if has_origin:
        by_origin = defaultdict(lambda: [0, 0])  # origin -> [qualified, total]
        for r in pop:
            o = r.get("origin") or "unknown"
            by_origin[o][1] += 1
            if r.get("is_qualified"):
                by_origin[o][0] += 1
        out["origin_survival"] = {
            o: {"qualified": q, "total": t, "qualified_rate": (q / t) if t else None}
            for o, (q, t) in sorted(by_origin.items(), key=lambda kv: -kv[1][1])
        }
    else:
        out["origin_survival"] = ("NOT COMPUTABLE: no origin/source tag. Add an origin TEXT column "
                                  "(seed / reseed / ga / negation / refine / universe_sweep) to track reseed survival.")
    return out


def _duplicate_rate(pop, sample=400, seed=0):
    exprs = [r.get("expression") for r in pop if r.get("expression")]
    if len(exprs) < 2:
        return None
    rng = random.Random(seed)
    if len(exprs) > sample:
        exprs = rng.sample(exprs, sample)
    motifs = [SyntaxValidator.structural_motifs(e) for e in exprs]
    dups = 0
    for i in range(1, len(exprs)):
        a = motifs[i]
        if not a:
            continue
        best = 0.0
        for j in range(i):
            b = motifs[j]
            if not b:
                continue
            u = len(a | b)
            if u:
                best = max(best, len(a & b) / u)
        if best >= getattr(config, "AST_DEDUP_SIMILARITY", 0.92):
            dups += 1
    return dups / (len(exprs) - 1)


# ===========================================================================
# 5. Grinold breadth ceiling
# ===========================================================================
def module5_grinold(enb):
    """IR ~= IC * sqrt(breadth). With effective breadth = ENB, frame the IR
    ceiling for a few plausible per-bet IC values. Pure framing -- we do not
    observe IC, so this shows the SHAPE of the ceiling, not a point forecast."""
    if not enb or enb <= 0:
        return {"available": False}
    out = {"effective_breadth": enb, "ir_ceiling_by_ic": {}}
    for ic in (0.02, 0.03, 0.05):
        out["ir_ceiling_by_ic"][str(ic)] = ic * math.sqrt(enb)
    return out


# ===========================================================================
# Scorecard
# ===========================================================================
def build_scorecard(m1, beh_all, beh_qual, m3, m4):
    """Roll modules into 0-100 sub-scores with explicit healthy targets. Each
    score is a transparent, monotone transform of one driver metric."""
    def clip01(x):
        return max(0.0, min(1.0, x))
    rows = []

    ent = m1.get("operator_entropy_norm")
    rows.append(("Operator diversity", "normalized operator entropy", "> 0.6",
                 round(ent, 3) if ent is not None else None,
                 round(100 * clip01(ent / 0.6), 1) if ent is not None else None))

    eff = m1.get("effective_field_count")
    rows.append(("Field diversity", "effective field count (1/HHI)", "> 8",
                 round(eff, 2) if eff is not None else None,
                 round(100 * clip01(eff / 8.0), 1) if eff is not None else None))

    maxn = m1.get("max_neut_share")
    rows.append(("Neutralization diversity", "max single-neut share", "< 0.5",
                 round(maxn, 3) if maxn is not None else None,
                 round(100 * clip01((1 - maxn) / 0.5), 1) if maxn is not None else None))

    beh = beh_qual if beh_qual.get("available") else beh_all
    enb = beh.get("enb_denoised") if beh.get("available") else None
    nq = beh.get("n_alphas_in_matrix") if beh.get("available") else None
    indep = (enb / nq) if (enb and nq) else None
    rows.append(("Behavioral independence", "denoised ENB / #alphas", "> 0.3",
                 round(indep, 3) if indep is not None else None,
                 round(100 * clip01(indep / 0.3), 1) if indep is not None else None))

    pbo = m3.get("pbo") if m3 else None
    rows.append(("Statistical validity", "PBO (prob. backtest overfit)", "< 0.3",
                 round(pbo, 3) if pbo is not None else None,
                 round(100 * clip01((1 - pbo) / 0.7), 1) if pbo is not None else None))

    lift = m4.get("best_fitness_lift_vs_seed")
    rows.append(("Search effectiveness", "evolved vs best-seed fitness lift", "> 0",
                 round(lift, 4) if lift is not None else None,
                 (100.0 if (lift is not None and lift > 0) else (0.0 if lift is not None else None))))

    sub_scores = [r[4] for r in rows if r[4] is not None]
    overall = round(sum(sub_scores) / len(sub_scores), 1) if sub_scores else None
    vanity = None
    if beh.get("available") and enb:
        vanity = round((nq / enb), 1) if enb else None
    return {"rows": rows, "overall": overall,
            "vanity_ratio_alphas_per_bet": vanity}


# ===========================================================================
# Cross-run history (SEPARATE db) + deltas
# ===========================================================================
def record_history(history_db, run_label, dataset, headline):
    conn = sqlite3.connect(history_db, timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, run_label TEXT, dataset TEXT, metrics_json TEXT
        )""")
    # Prefer this run's OWN previous entry (a true run-over-run delta); fall
    # back to the most recent entry of any label only when this label is new.
    # (The old `run_label != ? OR run_label = ?` was a tautology that just
    # grabbed the latest row regardless of which dataset produced it.)
    prev = conn.execute(
        "SELECT metrics_json FROM run_diagnostics WHERE run_label = ? "
        "ORDER BY id DESC LIMIT 1", (run_label,)).fetchone()
    if prev is None:
        prev = conn.execute(
            "SELECT metrics_json FROM run_diagnostics ORDER BY id DESC LIMIT 1").fetchone()
    prev_metrics = json.loads(prev[0]) if prev else None
    conn.execute(
        "INSERT INTO run_diagnostics (ts, run_label, dataset, metrics_json) VALUES (?,?,?,?)",
        (datetime.datetime.now().isoformat(timespec="seconds"), run_label, dataset,
         json.dumps(headline)))
    conn.commit()
    conn.close()
    deltas = {}
    if prev_metrics:
        for k, v in headline.items():
            pv = prev_metrics.get(k)
            if isinstance(v, (int, float)) and isinstance(pv, (int, float)):
                deltas[k] = round(v - pv, 4)
    return deltas


# ===========================================================================
# Reporting
# ===========================================================================
def _fmt(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def write_report(path, ctx):
    m1, beh_all, beh_qual = ctx["m1"], ctx["beh_all"], ctx["beh_qual"]
    m3, pbo, m4, m5 = ctx["m3"], ctx["pbo"], ctx["m4"], ctx["m5"]
    sc, deltas = ctx["scorecard"], ctx["deltas"]
    L = []
    L.append(f"# Run Diagnostics - {ctx['run_label']}")
    L.append(f"_dataset: {ctx['dataset']}  |  generated: {ctx['ts']}  |  scope: {ctx['scope']}_\n")
    L.append(f"DB: `{ctx['db']}` | alphas analyzed: {m1['n_alphas']} | "
             f"trials (true N): {m3['n_trials_true']}\n")

    L.append("## Run Health Scorecard")
    L.append("| Sub-score | Driver | Target | Value | Score (0-100) |")
    L.append("|---|---|---|---|---|")
    for name, driver, target, val, score in sc["rows"]:
        L.append(f"| {name} | {driver} | {target} | {_fmt(val)} | {_fmt(score,1)} |")
    L.append(f"\n**Overall health: {_fmt(sc['overall'],1)} / 100**")
    if sc.get("vanity_ratio_alphas_per_bet") is not None:
        L.append(f"**Vanity ratio: {_fmt(sc['vanity_ratio_alphas_per_bet'],1)} qualified alphas per independent bet** "
                 f"(higher = more redundant headcount).")
    if deltas:
        L.append("\n**Change vs previous run:** " +
                 ", ".join(f"{k} {('+' if v>=0 else '')}{v}" for k, v in deltas.items()))
    L.append("")

    L.append("## Module 1 - Structural / monoculture")
    L.append(f"- Operator coverage: {_fmt(m1['operator_coverage'])} "
             f"({m1['operators_used']}/{m1['operators_available']} ops used); "
             f"normalized entropy {_fmt(m1['operator_entropy_norm'])}")
    L.append(f"- Zero-usage operators ({len(m1['operators_zero_usage'])}): "
             f"{', '.join(m1['operators_zero_usage']) or 'none'}")
    L.append(f"- Neutralization style: {m1['neutralization_style']}")
    L.append(f"- Neutralization group key: {m1['neutralization_group_key']}")
    L.append(f"- Effective field count (1/HHI): {_fmt(m1['effective_field_count'],2)}; "
             f"effective family count: {_fmt(m1['effective_family_count'],2)}")
    L.append(f"- Family distribution: {m1['family_distribution']}")
    L.append(f"- Archetypes: {m1['n_distinct_skeletons']} distinct; "
             f"max archetype share {_fmt(m1['max_archetype_share'])}")
    L.append(f"- Top archetypes: {json.dumps(m1['archetype_distribution'], indent=0)}")
    L.append(f"- Depth {m1['depth']}")
    L.append(f"- Turnover {m1['turnover']}")
    L.append(f"- Decay {m1['decay']}")
    L.append(f"- Mean AST clone similarity: {_fmt(m1['ast_clone_similarity_mean'])}")
    L.append("")

    L.append("## Module 2 - Behavioral independence (Effective Number of Bets)")
    for label, beh in (("ALL with PnL", beh_all), ("QUALIFIED with PnL", beh_qual)):
        L.append(f"### {label}")
        if not beh.get("available"):
            L.append(f"- not available: {beh.get('reason')} (n_with_pnl={beh.get('n_with_pnl','?')})")
            continue
        L.append(f"- matrix: {beh['n_alphas_in_matrix']} alphas x {beh['n_days']} days "
                 f"(coverage {_fmt(beh['coverage'])}, q=N/T {_fmt(beh['q_ratio_N_over_T'])})")
        L.append(f"- **ENB raw {_fmt(beh['enb_raw'],2)} | ENB denoised {_fmt(beh['enb_denoised'],2)}** "
                 f"(MP lambda+ {_fmt(beh['mp_lambda_plus'],2)})")
        L.append(f"- PC1 share: raw {_fmt(beh['pc1_share_raw'])} / denoised {_fmt(beh['pc1_share_denoised'])}")
        L.append(f"- mean |corr|: {_fmt(beh['mean_abs_corr'])}; cluster count {beh['cluster_count']}")
        if beh.get("cluster_representatives"):
            L.append("- Behavioral clusters (representative = highest-fitness member):")
            for rep in beh["cluster_representatives"]:
                L.append(f"    - size {rep['size']}: {rep['alpha_id']} "
                         f"(fit {_fmt(rep['fitness'])}, sharpe {_fmt(rep['sharpe'])}) "
                         f"archetype `{rep['archetype']}`")
    L.append("")

    L.append("## Module 3 - Statistical validity")
    L.append(f"- DSR survivors (deflation prob >= {int(DSR_CONFIDENCE*100)}%): "
             f"{m3['dsr_survivors_true_N']}/{m3['n_scored']} at TRUE N={m3['n_trials_true']} "
             f"(vs {m3['dsr_survivors_capped_N']} at capped N={m3['n_trials_capped']})")
    L.append(f"- DSR survival rate (true N): {_fmt(m3['dsr_survival_rate_true_N'])}")
    if pbo and pbo.get("available"):
        L.append(f"- **PBO {_fmt(pbo['pbo'])}** over {pbo['n_partitions']} CSCV partitions "
                 f"({pbo['blocks']} blocks)")
    else:
        L.append(f"- PBO: not available ({(pbo or {}).get('reason','no data')})")
    if m3.get("oos_gap_flag"):
        L.append("- **DATA GAP:** oos_sharpe is empty for the whole run -- IS->OOS decay cannot be "
                 "validated. Wire OOS capture into the next run.")
    if m3.get("top_alphas_by_dsr"):
        L.append("- Top alphas by true-N DSR:")
        for t in m3["top_alphas_by_dsr"]:
            L.append(f"    - {t['alpha_id']}: DSR {_fmt(t['dsr_true_N'])}, "
                     f"MinTRL {_fmt(t['min_trl_years'],2)} yr")
    L.append("")

    L.append("## Module 4 - GA / search health")
    L.append(f"- Generations present: {m4['generations_present']}")
    L.append(f"- Best-fitness lift vs seed: {_fmt(m4['best_fitness_lift_vs_seed'],4)}")
    L.append(f"- Structural duplicate rate (wasted compute proxy): {_fmt(m4['structural_duplicate_rate'])}")
    if m4.get("per_generation"):
        L.append("- Per-generation collapse (gen: opEntropy / effFamilies / winnerRate / bestSharpe):")
        for p in m4["per_generation"]:
            L.append(f"    - g{p['generation']} (n={p['n']}): "
                     f"{_fmt(p['operator_entropy_norm'])} / {_fmt(p['effective_family_count'],2)} / "
                     f"{_fmt(p['winner_base_rate'])} / {_fmt(p['best_sharpe'])}")
    L.append("- Lineage / mutation / origin:")
    for k, v in m4["lineage"].items():
        if isinstance(v, dict):
            L.append(f"    - {k}: {json.dumps(v, default=str)}")
        else:
            L.append(f"    - {k}: {v}")
    L.append("")

    L.append("## Module 5 - Grinold breadth ceiling")
    if m5.get("available"):
        L.append(f"- Effective breadth (denoised ENB): {_fmt(m5['effective_breadth'],2)}")
        L.append(f"- IR ceiling by assumed per-bet IC: {m5['ir_ceiling_by_ic']}")
    else:
        L.append("- not available (no ENB)")
    L.append("")

    L.append("## Senior-dev caveats")
    L.append("- No single metric is a verdict. Read low ENB + high archetype concentration + "
             "negative GA lift TOGETHER.")
    L.append("- Behavioral numbers are only as good as PnL coverage (reported above). "
             "Denoised ENB is the honest headline; raw ENB overstates independence.")
    L.append("- Diagnostics describe; they do not fix. Record this baseline before changing the GA.")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


# ===========================================================================
# Optional plots
# ===========================================================================
def write_plots(out_dir, ctx):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []
    written = []
    m4 = ctx["m4"]
    if m4.get("per_generation"):
        gens = [p["generation"] for p in m4["per_generation"]]
        ent = [p["operator_entropy_norm"] or 0 for p in m4["per_generation"]]
        fig, ax = plt.subplots()
        ax.plot(gens, ent, marker="o")
        ax.set_xlabel("generation"); ax.set_ylabel("operator entropy (norm)")
        ax.set_title("Diversity collapse over generations")
        p = os.path.join(out_dir, "diversity_over_gen.png")
        fig.savefig(p, bbox_inches="tight"); plt.close(fig); written.append(p)
    op = ctx["m1"].get("operator_usage", {})
    if op:
        items = list(op.items())[:20]
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1])
        ax.set_title("Operator usage (top 20)")
        p = os.path.join(out_dir, "operator_usage.png")
        fig.savefig(p, bbox_inches="tight"); plt.close(fig); written.append(p)
    return written


# ===========================================================================
# Orchestration
# ===========================================================================
def run(args):
    conn = open_readonly(args.db)
    try:
        pop_all = load_population(conn, "all")
        pop_qual = load_population(conn, "qualified")
        if not pop_all:
            print("[run_diagnostics] no simulated alphas found; nothing to do.")
            return
        scope_pop = pop_qual if args.scope == "qualified" else pop_all
        n_trials_true = len(pop_all)

        by_id_all = {r["alpha_id"]: r for r in pop_all if r.get("alpha_id")}
        ids_all = [r["alpha_id"] for r in pop_all if r.get("alpha_id")]
        ids_qual = [r["alpha_id"] for r in pop_qual if r.get("alpha_id")]
        ret_all = load_pnl_returns(conn, ids_all)
        ret_qual = {a: ret_all[a] for a in ids_qual if a in ret_all}

        m1 = module1_structural(scope_pop)
        beh_all = module2_behavioral(ret_all, by_id_all, "all")
        beh_qual = module2_behavioral(ret_qual, by_id_all, "qualified")
        m3 = module3_statistical(scope_pop, n_trials_true)

        # CSCV on the behavioral matrix (prefer qualified, else all).
        built = build_return_matrix(ret_qual) or build_return_matrix(ret_all)
        pbo = cscv_pbo(built[2]) if built else {"available": False, "reason": "no return matrix"}
        if pbo.get("available"):
            m3["pbo"] = pbo["pbo"]

        m4 = module4_search(scope_pop, ret_all)
        beh_for_grinold = beh_qual if beh_qual.get("available") else beh_all
        m5 = module5_grinold(beh_for_grinold.get("enb_denoised") if beh_for_grinold.get("available") else None)
        scorecard = build_scorecard(m1, beh_all, beh_qual, m3, m4)
    finally:
        conn.close()

    headline = {
        "operator_entropy_norm": m1.get("operator_entropy_norm"),
        "effective_field_count": m1.get("effective_field_count"),
        "max_neut_share": m1.get("max_neut_share"),
        "enb_denoised_qualified": beh_qual.get("enb_denoised") if beh_qual.get("available") else None,
        "enb_denoised_all": beh_all.get("enb_denoised") if beh_all.get("available") else None,
        "pbo": m3.get("pbo"),
        "dsr_survival_rate_true_N": m3.get("dsr_survival_rate_true_N"),
        "best_fitness_lift_vs_seed": m4.get("best_fitness_lift_vs_seed"),
        "overall_health": scorecard.get("overall"),
        "vanity_ratio": scorecard.get("vanity_ratio_alphas_per_bet"),
    }
    run_label = args.run_label or os.path.splitext(os.path.basename(args.db))[0]
    dataset = getattr(config, "WQ_DATASET_ID", "") or "unknown"
    deltas = record_history(args.history_db, run_label, dataset, headline)

    os.makedirs(args.out_dir, exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    ctx = {"db": args.db, "run_label": run_label, "dataset": dataset, "ts": ts,
           "scope": args.scope, "m1": m1, "beh_all": beh_all, "beh_qual": beh_qual,
           "m3": m3, "pbo": pbo, "m4": m4, "m5": m5, "scorecard": scorecard,
           "deltas": deltas}
    report_path = os.path.join(args.out_dir, "run_report.md")
    metrics_path = os.path.join(args.out_dir, "run_metrics.json")
    write_report(report_path, ctx)
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump({"headline": headline, "deltas": deltas, "module1": m1,
                   "behavioral_all": beh_all, "behavioral_qualified": beh_qual,
                   "statistical": m3, "cscv": pbo, "search": m4, "grinold": m5,
                   "scorecard": scorecard}, fh, indent=2, default=str)
    plots = write_plots(args.out_dir, ctx) if args.plots else []

    print(f"[run_diagnostics] {run_label}: overall health {headline['overall_health']}/100")
    print(f"  report:  {report_path}")
    print(f"  metrics: {metrics_path}")
    if plots:
        print(f"  plots:   {', '.join(plots)}")
    if deltas:
        print(f"  vs prev: {deltas}")


def main():
    ap = argparse.ArgumentParser(description="Read-only BrainForge run diagnostics / post-mortem.")
    ap.add_argument("--db", default=os.getenv("BRAINFORGE_DB", "brain_memory.db"),
                    help="run database to analyze (opened read-only)")
    ap.add_argument("--scope", choices=["all", "qualified"], default="all",
                    help="population scope for structural/GA/DSR modules (ENB is always computed for both)")
    ap.add_argument("--out-dir", default="diagnostics_out")
    ap.add_argument("--history-db", default=os.getenv("WQ_DIAGNOSTICS_HISTORY", "diagnostics_history.db"),
                    help="SEPARATE cross-run metrics DB (never the run DB)")
    ap.add_argument("--run-label", default=None, help="label for cross-run tracking (defaults to db filename)")
    ap.add_argument("--plots", action="store_true", help="emit PNG plots (requires matplotlib)")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
