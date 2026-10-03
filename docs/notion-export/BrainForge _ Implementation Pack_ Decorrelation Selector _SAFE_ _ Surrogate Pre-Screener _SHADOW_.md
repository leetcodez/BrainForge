<callout icon="⚠️" color="yellow_bg">
	I can't push to your repo or local disk — these are complete, paste-ready files. **Before you touch anything:** `cp brain_memory.earnings4_run2.db brain_memory.earnings4_run2.db.bak`
	**Two things, classified by risk:**
	- **Part 1 — PnL Decorrelation Selector** → *SAFE / off-to-the-side.* Runs after generation, never touches the GA loop. Additive DB table only. Build & run now.
	- **Part 2 — Surrogate Pre-Screener** → *RISKY (hot path).* Ships in **SHADOW MODE**: it only logs what it *would* skip and an offline evaluator reports its accuracy. It never gates a simulation until you flip a flag, and only after the numbers justify it.
</callout>
# Part 1 — PnL Decorrelation Selector (SAFE)
Goal: stop submitting near-duplicate alphas that collapse to one alpha's marginal value and blow the per-bucket cap. We persist each qualified alpha's daily PnL, compute the real pairwise Pearson matrix, and greedily pick the largest mutually-decorrelated basket under a correlation budget. **Submits nothing on its own** — `submit_to_worldquant.py` consumes its ordering.
## 1a. `db_manager.py` — additive `alpha_pnl` table
All changes are `CREATE TABLE IF NOT EXISTS` / new methods. No existing row or column is touched.
**Inside ****`_init_schema`****, right after the ****`CREATE INDEX ... idx_generation`**** line and before ****`DatabaseManager._migrate_schema(conn)`****, add:**
```python
# --- daily PnL store for the decorrelation selector (additive) -------
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS alpha_pnl (
        alpha_id  TEXT NOT NULL,
        date      TEXT NOT NULL,
        pnl       REAL,
        PRIMARY KEY (alpha_id, date)
    )
    """
)
conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_alpha ON alpha_pnl(alpha_id)")
```
**Add these static methods (next to ****`_get_submission_candidates`****):**
```python
@staticmethod
def _save_pnl(conn, alpha_id, series):
    # series: iterable of (date_str, cumulative_pnl_float). Idempotent upsert
    # so re-running the backfill never duplicates or corrupts a series.
    conn.executemany(
        """
        INSERT INTO alpha_pnl (alpha_id, date, pnl)
        VALUES (?, ?, ?)
        ON CONFLICT(alpha_id, date) DO UPDATE SET pnl = excluded.pnl
        """,
        [(alpha_id, d, p) for d, p in series],
    )

@staticmethod
def _load_pnl(conn, alpha_id):
    cursor = conn.execute(
        "SELECT date, pnl FROM alpha_pnl WHERE alpha_id = ? ORDER BY date ASC",
        (alpha_id,),
    )
    return cursor.fetchall()

@staticmethod
def _alpha_ids_with_pnl(conn):
    cursor = conn.execute("SELECT DISTINCT alpha_id FROM alpha_pnl")
    return [row[0] for row in cursor.fetchall()]
```
**Add the matching sync wrappers (next to ****`get_submission_candidates_sync`****):**
```python
def save_pnl_sync(self, alpha_id, series):
    with self._sync_lock:
        self._save_pnl(self._sync_connection(), alpha_id, series)

def load_pnl_sync(self, alpha_id):
    with self._sync_lock:
        return self._load_pnl(self._sync_connection(), alpha_id)

def alpha_ids_with_pnl_sync(self):
    with self._sync_lock:
        return self._alpha_ids_with_pnl(self._sync_connection())
```
## 1b. `config.py` — selector knobs
Append after the `MAX_SUBMISSIONS_PER_RUN` block:
```python
# --- PnL-based decorrelation submission selector ----------------------------
# WorldQuant endpoint that returns an alpha's daily PnL recordset. Parsed
# DEFENSIVELY (list-of-[date, value] OR list-of-dicts), so a minor schema
# difference degrades to "no PnL" instead of crashing. Adjust if your tenant
# exposes a different path (e.g. /recordsets/daily-pnl).
WQ_PNL_ENDPOINT_TEMPLATE = os.getenv("WQ_PNL_ENDPOINT", "/alphas/{alpha_id}/recordsets/pnl")
# Soft correlation budget: a candidate is preferred while its max |PnL corr|
# with the already-selected basket stays at/under SOFT. HARD is WorldQuant's
# rejection ceiling (== MAX_SELF_CORRELATION) used only to backfill spare slots.
SUBMISSION_CORR_SOFT = float(os.getenv("WQ_SUBMISSION_CORR_SOFT", "0.50"))
SUBMISSION_CORR_HARD = float(os.getenv("WQ_SUBMISSION_CORR_HARD", "0.70"))
# Minimum overlapping trading days before a pairwise correlation is trusted.
SUBMISSION_CORR_MIN_OVERLAP = int(os.getenv("WQ_SUBMISSION_CORR_MIN_OVERLAP", "30"))
# Order/filter submissions with the PnL selector when stored PnL is available.
# Falls back to the existing AST-similarity _diversified_order when PnL is
# missing, so enabling it can NEVER break current behaviour.
SUBMISSION_USE_PNL_SELECTOR = os.getenv("WQ_SUBMISSION_USE_PNL_SELECTOR", "1").strip().lower() in ("1", "true", "yes", "on")
```
## 1c. `backfill_pnl.py` (new file)
Reads `alpha_id`s from `alpha_population`, fetches each alpha's daily PnL from BRAIN, writes to `alpha_pnl`. **Never touches the orchestrator.** Point `BRAINFORGE_DB` at the `.bak` copy if you want total isolation.
```python
"""Backfill daily PnL for qualified alphas into the alpha_pnl table.

Runs entirely OFF TO THE SIDE of the orchestrator: it only READS alpha_ids from
alpha_population and WRITES the new alpha_pnl table, so it cannot affect the
running generator.

Usage:
    python backfill_pnl.py             # fetch PnL for all qualified candidates
    python backfill_pnl.py --dry-run   # show what WOULD be fetched, store nothing
    python backfill_pnl.py --all       # every alpha with a real id, not just qualified
"""
import argparse
import asyncio

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine


def _parse_pnl_records(payload):
    """Defensively extract [(date, cumulative_pnl)] from a WQ pnl recordset.
    Handles {records: [[date, val], ...]} and {records: [{date:.., pnl:..}, ...]}."""
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


async def _fetch_pnl(net, alpha_id):
    endpoint = config.WQ_PNL_ENDPOINT_TEMPLATE.format(alpha_id=alpha_id)
    resp = await net.request("GET", endpoint)
    if resp["status_code"] not in (200, 201):
        return []
    return _parse_pnl_records(resp.get("json") or {})


async def main(dry_run=False, include_all=False):
    db = DatabaseManager()
    db.init_db_sync()
    if include_all:
        rows = db.get_top_population_sync(limit=1000000)
        alpha_ids = sorted({r[10] for r in rows if r[10] and r[10] != "MANUAL_SEED"})
    else:
        candidates = db.get_submission_candidates_sync(
            config.MIN_SHARPE, config.MAX_TURNOVER, config.MAX_SELF_CORRELATION,
            min_turnover=getattr(config, "MIN_TURNOVER", 0.0),
        )
        alpha_ids = sorted({c[1] for c in candidates if c[1] and c[1] != "MANUAL_SEED"})

    already = set(db.alpha_ids_with_pnl_sync())
    todo = [a for a in alpha_ids if a not in already]
    print(f"{len(alpha_ids)} target alpha(s); {len(already)} already stored; {len(todo)} to fetch.")
    if dry_run:
        for a in todo:
            print(f"  would fetch PnL for {a}")
        db.close_sync()
        return

    net = NetworkEngine()
    stored = 0
    try:
        for alpha_id in todo:
            series = await _fetch_pnl(net, alpha_id)
            if not series:
                print(f"  no PnL returned for {alpha_id} (skipped)")
                continue
            db.save_pnl_sync(alpha_id, series)
            stored += 1
            print(f"  stored {len(series)} PnL points for {alpha_id}")
    finally:
        await net.close()
        db.close_sync()
    print(f"Done. Stored PnL for {stored} alpha(s).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", dest="include_all")
    args = ap.parse_args()
    asyncio.run(main(dry_run=args.dry_run, include_all=args.include_all))
```
## 1d. `decorrelation_selector.py` (new file)
The selector itself — pure computation + report. Submits nothing.
```python
"""PnL-correlation-budgeted submission selector.

Given the qualified submission candidates and their stored daily PnL, pick the
largest basket of MUTUALLY DECORRELATED alphas (greedy maximum-impact under a
PnL-correlation budget). Three passes: (1) strict SOFT budget, (2) relax to the
HARD ceiling to fill spare slots, (3) candidates with no PnL on file appended by
impact as a last resort.

This module SUBMITS NOTHING. submit_to_worldquant.py consumes select_submissions().

Dry-run report:
    python decorrelation_selector.py
"""
import numpy as np

import config
from db_manager import DatabaseManager


def _f(x):
    return f"{x:.4f}" if isinstance(x, (int, float)) else "n/a"


def _daily_returns(pnl_rows):
    """(date, cumulative_pnl) rows -> dict(date -> daily change)."""
    dates = [d for d, _ in pnl_rows]
    vals = [p for _, p in pnl_rows]
    out = {}
    for i in range(1, len(vals)):
        if vals[i] is None or vals[i - 1] is None:
            continue
        out[dates[i]] = vals[i] - vals[i - 1]
    return out


def _pairwise_corr(a, b):
    """Pearson over shared dates; None when overlap < SUBMISSION_CORR_MIN_OVERLAP
    or either series is flat (std 0)."""
    common = sorted(set(a) & set(b))
    if len(common) < config.SUBMISSION_CORR_MIN_OVERLAP:
        return None
    va = np.array([a[d] for d in common], dtype=float)
    vb = np.array([b[d] for d in common], dtype=float)
    if va.std() == 0 or vb.std() == 0:
        return None
    return float(np.corrcoef(va, vb)[0, 1])


def select_submissions(db=None, verbose=False):
    """Return an ordered list of selected candidate tuples
    (expr, alpha_id, sharpe, turnover, fitness, max_corr) under the PnL budget."""
    own_db = db is None
    if own_db:
        db = DatabaseManager()
        db.init_db_sync()
    candidates = db.get_submission_candidates_sync(
        config.MIN_SHARPE, config.MAX_TURNOVER, config.MAX_SELF_CORRELATION,
        min_turnover=getattr(config, "MIN_TURNOVER", 0.0),
    )
    # Impact = deflated fitness (index 4), highest first.
    ranked = sorted(candidates,
                    key=lambda c: c[4] if c[4] is not None else float("-inf"),
                    reverse=True)
    returns = {}
    for c in ranked:
        rows = db.load_pnl_sync(c[1])
        if rows:
            returns[c[1]] = _daily_returns(rows)

    soft = config.SUBMISSION_CORR_SOFT
    hard = config.SUBMISSION_CORR_HARD
    cap = config.MAX_SUBMISSIONS_PER_RUN

    def worst_corr(aid, chosen):
        r = returns.get(aid)
        if r is None:
            return None
        w = 0.0
        for s in chosen:
            sr = returns.get(s[1])
            if not sr:
                continue
            corr = _pairwise_corr(r, sr)
            if corr is not None:
                w = max(w, abs(corr))
        return w

    selected = []
    # Pass 1: strict soft budget.
    for c in ranked:
        if len(selected) >= cap:
            break
        w = worst_corr(c[1], selected)
        if w is not None and w <= soft:
            selected.append(c)
            if verbose:
                print(f"[pass1] SELECT {c[1]} fitness={_f(c[4])} worstcorr={w:.3f}")
    # Pass 2: relax to the HARD ceiling to fill spare slots (impact order).
    for c in ranked:
        if len(selected) >= cap:
            break
        if c in selected:
            continue
        w = worst_corr(c[1], selected)
        if w is not None and w <= hard:
            selected.append(c)
            if verbose:
                print(f"[pass2] SELECT {c[1]} fitness={_f(c[4])} worstcorr={w:.3f}")
    # Pass 3: no PnL on file -> append by impact (cannot verify; last resort).
    for c in ranked:
        if len(selected) >= cap:
            break
        if c in selected:
            continue
        if returns.get(c[1]) is None:
            selected.append(c)
            if verbose:
                print(f"[pass3] SELECT {c[1]} (no PnL on file; fitness order)")
    if own_db:
        db.close_sync()
    return selected


def _report():
    db = DatabaseManager()
    db.init_db_sync()
    selected = select_submissions(db=db, verbose=True)
    print("\n=== Recommended submission order ===")
    for i, c in enumerate(selected, 1):
        print(f"{i:2d}. {c[1]}  fitness={_f(c[4])} sharpe={_f(c[2])} turnover={_f(c[3])}")
        print(f"      {c[0]}")
    if not selected:
        print("(no candidates — run backfill_pnl.py first, or check the gate)")
    db.close_sync()


if __name__ == "__main__":
    _report()
```
## 1e. `submit_to_worldquant.py` — gated integration + dry-run
Keep `_data_category`, `_live_failed_checks`, and `_diversified_order` exactly as they are. **Add the import** at the top:
```python
from decorrelation_selector import select_submissions
```
**Replace ****`submit()`**** and the ****`__main__`**** block with:**
```python
async def submit(dry_run=False):
    """Submit the best qualifying alphas. When SUBMISSION_USE_PNL_SELECTOR is on
    and stored PnL exists, ordering comes from the PnL-decorrelation selector;
    otherwise it falls back to the AST-similarity _diversified_order, so this is
    a strict superset of the old behaviour. --dry-run prints the plan and POSTs
    nothing."""
    db = DatabaseManager()
    db.init_db_sync()
    candidates = db.get_submission_candidates_sync(
        config.MIN_SHARPE, config.MAX_TURNOVER, config.MAX_SELF_CORRELATION,
        min_turnover=getattr(config, "MIN_TURNOVER", 0.0),
    )
    if not candidates:
        print("No submission candidates meet the gate.")
        db.close_sync()
        return

    if getattr(config, "SUBMISSION_USE_PNL_SELECTOR", False):
        ordered = select_submissions(db=db) or _diversified_order(candidates)
    else:
        ordered = _diversified_order(candidates)

    if dry_run:
        print(f"DRY RUN — {len(ordered)} alpha(s) would be submitted (cap "
              f"{config.MAX_SUBMISSIONS_PER_RUN}), in order:")
        for i, (expr, alpha_id, sharpe, turnover, fitness, max_corr) in enumerate(ordered, 1):
            corr_txt = f"{max_corr:.3f}" if max_corr is not None else "n/a"
            print(f"{i:2d}. {alpha_id} sharpe={sharpe:.3f} turnover={turnover:.3f} "
                  f"fitness={fitness:.4f} stored_self_corr={corr_txt}")
            print(f"      {expr}")
        db.close_sync()
        return

    net = NetworkEngine()
    submitted = 0
    try:
        for expr, alpha_id, sharpe, turnover, fitness, max_corr in ordered:
            if submitted >= config.MAX_SUBMISSIONS_PER_RUN:
                print(f"Reached submission cap ({config.MAX_SUBMISSIONS_PER_RUN}).")
                break
            if not alpha_id or alpha_id == "MANUAL_SEED":
                continue
            failed = await _live_failed_checks(net, alpha_id)
            if failed:
                print(f"Skipping {alpha_id}: BRAIN checks still failing -> {failed}")
                continue
            res = await net.request("POST", f"/alphas/{alpha_id}/submit")
            if res["status_code"] in (200, 201):
                submitted += 1
                corr_txt = f"{max_corr:.3f}" if max_corr is not None else "n/a"
                print(f"Submitted {alpha_id} | sharpe={sharpe:.3f} turnover={turnover:.3f} "
                      f"fitness={fitness:.4f} self_corr={corr_txt}")
            else:
                print(f"Submit failed for {alpha_id}: HTTP {res['status_code']} -> {res['json']}")
    finally:
        await net.close()
        db.close_sync()
    print(f"Done. Submitted {submitted} alpha(s).")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(submit(dry_run=args.dry_run))
```
## 1f. How to test by reading (no submissions)
1. Back up: `cp brain_memory.earnings4_run2.db brain_memory.earnings4_run2.db.bak`
2. Point at the copy: `export BRAINFORGE_DB=brain_memory.earnings4_run2.db.bak`
3. See what PnL it would pull: `python backfill_pnl.py --dry-run`
4. Actually fetch PnL into the copy: `python backfill_pnl.py`
5. **Read the plan:** `python decorrelation_selector.py` — shows the recommended order and which pass admitted each pick (pass1 = under 0.50, pass2 = under 0.70, pass3 = unverified).
6. **Read the full submit plan without submitting:** `python submit_to_worldquant.py --dry-run`
What to look for: the selector should keep the highest-fitness alpha of each correlated cluster and drop its siblings. If your \~97 qualified candidates really collapse to \~3–6 independent bets, you'll see pass1 select a handful, pass2 add a couple, and the rest never appear. That confirms it's working before a single real submission.
---
# Part 2 — Surrogate Pre-Screener (SHADOW MODE)
This is the one that sits in the hot path, so it ships **disabled and shadow-only**. It trains a cheap classifier on `alpha_population` to predict whether a candidate is worth simulating, then an **offline evaluator** tells you its false-negative rate. It does not — and cannot, with the defaults below — skip any simulation.
## 2a. `config.py` — surrogate knobs (all default to OFF/shadow)
```python
# --- Surrogate pre-screener (SHADOW MODE ONLY by default) -------------------
# A cheap model that PREDICTS whether a candidate is worth simulating. OFF the
# hot path by default: SHADOW only LOGS what it WOULD skip and never blocks a
# simulation, so it cannot starve the generator. Promote to a soft prioritizer
# ONLY after evaluate_prescreener.py shows an acceptable false-negative rate.
SURROGATE_ENABLED = os.getenv("WQ_SURROGATE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
SURROGATE_SHADOW_ONLY = os.getenv("WQ_SURROGATE_SHADOW_ONLY", "1").strip().lower() in ("1", "true", "yes", "on")
SURROGATE_MODEL_PATH = os.getenv("WQ_SURROGATE_MODEL", str(Path(__file__).with_name("surrogate_model.pkl")))
# Label: a row is a "winner" if it cleared this Sharpe AND sits in the turnover
# band. Keep aligned with the promotion gate.
SURROGATE_WINNER_SHARPE = float(os.getenv("WQ_SURROGATE_WINNER_SHARPE", "1.25"))
# Probability below which SHADOW mode would (only logs!) consider skipping a sim.
SURROGATE_SKIP_THRESHOLD = float(os.getenv("WQ_SURROGATE_SKIP_THRESHOLD", "0.10"))
```
## 2b. `surrogate_prescreener.py` (new file)
```python
"""Cheap surrogate model that predicts whether a candidate alpha is worth a real
simulation. SHADOW-SAFE: this module only TRAINS and SCORES. Nothing here gates
the orchestrator. Featurization is pure-stdlib AST + config.field_family, so it
adds no runtime cost beyond a dict lookup.

    python surrogate_prescreener.py        # train on alpha_population, save model
"""
import ast
import pickle

import config
from db_manager import DatabaseManager

_FAMILIES = ["options_vol", "earnings_event", "analyst", "fundamental",
             "sentiment", "macro", "relationship", "price_volume"]
_GATE_OPS = ("trade_when", "keep")


def _ast_depth(tree):
    if tree is None:
        return 1
    def d(n):
        ch = list(ast.iter_child_nodes(n))
        return 1 + max((d(c) for c in ch), default=0)
    return d(tree)


def feature_names():
    base = ["expr_len", "ast_depth", "n_calls", "n_unique_ops", "n_gate_ops",
            "has_group_neutralize", "decay"]
    return base + [f"fam_{f}" for f in _FAMILIES] + [f"univ_{u}" for u in config.UNIVERSES]


def featurize(expression, universe="TOP3000", decay=0):
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        tree = None
    nodes = list(ast.walk(tree)) if tree else []
    call_nodes = [n for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    op_names = [n.func.id.lower() for n in call_nodes]
    names = [n.id for n in nodes if isinstance(n, ast.Name)]
    feats = [
        float(len(expression or "")),
        float(_ast_depth(tree)),
        float(len(call_nodes)),
        float(len(set(op_names))),
        float(sum(1 for o in op_names if o in _GATE_OPS)),
        1.0 if "group_neutralize" in op_names else 0.0,
        float(decay or 0),
    ]
    fam_counts = {f: 0 for f in _FAMILIES}
    for nm in names:
        fam = config.field_family(nm)
        if fam in fam_counts:
            fam_counts[fam] += 1
    feats += [float(fam_counts[f]) for f in _FAMILIES]
    feats += [1.0 if universe == u else 0.0 for u in config.UNIVERSES]
    return feats


def _is_winner(sharpe, turnover):
    if sharpe is None:
        return 0
    if sharpe < config.SURROGATE_WINNER_SHARPE:
        return 0
    t = turnover if turnover is not None else 0.0
    if t < getattr(config, "MIN_TURNOVER", 0.0) or t > config.MAX_TURNOVER:
        return 0
    return 1


def load_dataset(db=None):
    own = db is None
    if own:
        db = DatabaseManager(); db.init_db_sync()
    rows = db.load_history_sync()  # (expr, universe, decay, sharpe, turnover, ...)
    X, y = [], []
    for expr, universe, decay, sharpe, turnover, *_ in rows:
        if sharpe is None:
            continue
        X.append(featurize(expr, universe, decay))
        y.append(_is_winner(sharpe, turnover))
    if own:
        db.close_sync()
    return X, y


def _new_classifier():
    try:
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=200, max_depth=-1, learning_rate=0.05,
                              subsample=0.8, class_weight="balanced")
    except Exception:
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                          learning_rate=0.05)


def train(model_path=None):
    X, y = load_dataset()
    pos = sum(y)
    print(f"Training rows: {len(y)} | winners: {pos} | losers: {len(y) - pos}")
    if len(y) < 50 or pos < 10 or pos == len(y):
        print("Not enough class balance to train a trustworthy model. Aborting.")
        return None
    clf = _new_classifier()
    clf.fit(X, y)
    path = model_path or config.SURROGATE_MODEL_PATH
    with open(path, "wb") as fh:
        pickle.dump({"model": clf, "features": feature_names()}, fh)
    print(f"Saved surrogate model -> {path}")
    return clf


_CACHE = {}


def _load_model():
    if "model" not in _CACHE:
        try:
            with open(config.SURROGATE_MODEL_PATH, "rb") as fh:
                _CACHE["model"] = pickle.load(fh)["model"]
        except Exception:
            _CACHE["model"] = None
    return _CACHE["model"]


def score(expression, universe="TOP3000", decay=0):
    """Predicted P(winner) in [0, 1], or None when no model is available.
    SHADOW callers must treat None / low scores as advisory only."""
    model = _load_model()
    if model is None:
        return None
    try:
        return float(model.predict_proba([featurize(expression, universe, decay)])[0][1])
    except Exception:
        return None


if __name__ == "__main__":
    train()
```
## 2c. `evaluate_prescreener.py` (new file) — the "read what it does" tool
```python
"""Offline, read-only evaluation of the surrogate pre-screener.

Trains on a time-ordered split of alpha_population and reports, at several skip
thresholds, how many simulations it WOULD have saved and how many real winners
it WOULD have wrongly skipped (false negatives). Run this BEFORE ever enabling
the surrogate on the hot path.

    python evaluate_prescreener.py
"""
import numpy as np

import config
from surrogate_prescreener import load_dataset, _new_classifier


def main():
    X, y = load_dataset()
    X, y = np.array(X, dtype=float), np.array(y, dtype=int)
    n = len(y)
    if n < 80 or y.sum() < 10:
        print(f"Too little data/balance to evaluate (rows={n}, winners={int(y.sum())}).")
        return
    cut = int(n * 0.7)  # train on the earlier 70%, test on the held-out 30%
    clf = _new_classifier()
    clf.fit(X[:cut], y[:cut])
    proba = clf.predict_proba(X[cut:])[:, 1]
    yt = y[cut:]
    total_winners = int(yt.sum())
    print(f"Test rows: {len(yt)} | winners in test: {total_winners}")
    print(f"{'thresh':>7} {'skipped%':>9} {'winners_lost':>13} {'FNR%':>7}")
    for thr in (0.02, 0.05, 0.10, 0.15, 0.20, 0.30):
        would_skip = proba < thr
        skipped_pct = 100.0 * would_skip.mean()
        winners_lost = int((would_skip & (yt == 1)).sum())
        fnr = 100.0 * winners_lost / total_winners if total_winners else 0.0
        print(f"{thr:>7.2f} {skipped_pct:>9.1f} {winners_lost:>13d} {fnr:>7.1f}")
    print("\nRead this as: at threshold T we skip skipped% of sims but lose FNR% of"
          " real winners. Only enable gating at a T where FNR is near 0.")


if __name__ == "__main__":
    main()
```
## 2d. Optional orchestrator hook (leave commented / disabled)
The surrogate is **not** wired into the loop. When `evaluate_prescreener.py` convinces you, add it as a **soft prioritizer** (reorder, never drop). Illustrative only — keep `SURROGATE_SHADOW_ONLY=1`:
```python
# In AlphaFactory, where a batch of candidate (expression, universe, decay) is
# about to be simulated:
#
# import surrogate_prescreener
# if config.SURROGATE_ENABLED:
#     scored = [(surrogate_prescreener.score(e, u, d), (e, u, d)) for e, u, d in batch]
#     if config.SURROGATE_SHADOW_ONLY:
#         would_skip = [c for s, c in scored if s is not None and s < config.SURROGATE_SKIP_THRESHOLD]
#         logger.info(f"[surrogate-shadow] would deprioritize {len(would_skip)}/{len(batch)} "
#                     f"candidates this batch (NOT skipped).")
#     else:
#         # SOFT prioritizer only: simulate ALL, just highest-score first.
#         batch = [c for _, c in sorted(scored, key=lambda x: (x[0] is None, -(x[0] or 0)))]
```
Note there is **no hard-filter branch** anywhere in this snippet — by design. The most it ever does is reorder.
## 2e. How to test by reading
1. Train: `python surrogate_prescreener.py` (aborts itself if classes are too imbalanced).
2. **Read the verdict:** `python evaluate_prescreener.py` — the table tells you, per threshold, how many sims you'd save vs. how many real winners you'd lose. If even a tiny threshold (0.02) loses winners, the surrogate is not safe to gate — leave it shadow-only.
3. Nothing here changes generation behaviour. `SURROGATE_ENABLED` stays `0`.
---
# Deferred (deliberately) — to keep risk low
- **WinnerMemory (labeling-only)** and **Decorrelated Success Exemplars** are safe but lower-value, and bolting on half-built versions would dilute review quality. The decorrelation selector already captures the immediate payoff. Add these later as separate, additive reporting passes.
- **`requirements.txt`****:** add `lightgbm` (optional — falls back to `scikit-learn`, which you likely already have). `numpy` is already a dependency.
# Apply / rollback checklist
1. `cp brain_memory.earnings4_run2.db brain_memory.earnings4_run2.db.bak`
2. Add the `alpha_pnl` table block + methods to `db_manager.py` (additive).
3. Append the config knobs to `config.py`.
4. Drop in `backfill_pnl.py`, `decorrelation_selector.py`, `surrogate_prescreener.py`, `evaluate_prescreener.py`.
5. Patch `submit_to_worldquant.py` (import + new `submit()` + `__main__`).
6. Test by reading: `backfill_pnl.py --dry-run` → `backfill_pnl.py` → `decorrelation_selector.py` → `submit_to_worldquant.py --dry-run` → `evaluate_prescreener.py`.
7. Rollback if anything looks off: restore the `.bak`, `git checkout` the touched files. The orchestrator was never modified, so a running generator is unaffected throughout.