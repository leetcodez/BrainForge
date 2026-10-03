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
import datetime

import numpy as np

import config
from db_manager import DatabaseManager


def _f(x):
    return f"{x:.4f}" if isinstance(x, (int, float)) else "n/a"


def _daily_returns(pnl_rows, max_gap_days=4):
    """Cumulative levels -> changes keyed by exact (start_date,end_date).
    Interval keys prevent two different missing-date patterns being compared
    merely because the increments end on the same date.
    """
    from forge2_statistics import daily_changes
    return daily_changes(dict(pnl_rows),max_gap_days)


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

    # Honesty gate: if too few candidates actually have stored daily PnL, this
    # selector cannot verify decorrelation and would silently collapse into
    # "top-N by fitness" (Pass 3 below). Return [] so submit_to_worldquant falls
    # back to the AST-similarity / category-cap _diversified_order instead of
    # pretending a PnL-decorrelated basket was produced. Run backfill_pnl.py to
    # raise coverage.
    min_cov = getattr(config, "SUBMISSION_MIN_PNL_COVERAGE", 0.5)
    coverage = (len(returns) / len(ranked)) if ranked else 0.0
    if ranked and coverage < min_cov:
        if verbose:
            print(f"[selector] PnL coverage {coverage:.0%} "
                  f"({len(returns)}/{len(ranked)}) < {min_cov:.0%}; deferring to "
                  f"the AST/category selector (run backfill_pnl.py to enable PnL "
                  f"decorrelation).")
        if own_db:
            db.close_sync()
        return []

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
                return None
            corr = _pairwise_corr(r, sr)
            if corr is None:
                return None
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
    # Pass 3: a FEW candidates may still lack PnL (overall coverage already
    # passed the min_cov gate above). Append them by impact as a last resort,
    # clearly flagged as correlation-UNVERIFIED so the basket is never silently
    # padded with unchecked alphas.
    unverified = 0
    for c in ranked:
        if len(selected) >= cap:
            break
        if c in selected:
            continue
        if returns.get(c[1]) is None and getattr(config,"ALLOW_UNVERIFIED_PNL_SELECTION",False):
            selected.append(c)
            unverified += 1
            if verbose:
                print(f"[pass3] SELECT {c[1]} (no PnL on file; correlation UNVERIFIED)")
    if unverified and verbose:
        print(f"[selector] {unverified}/{len(selected)} selected alpha(s) are "
              f"correlation-UNVERIFIED (no stored PnL).")
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
        print("(no candidates -- run backfill_pnl.py first, or check the gate)")
    db.close_sync()


if __name__ == "__main__":
    _report()
