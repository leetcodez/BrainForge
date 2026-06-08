import asyncio
import re

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine
from oos_deflation import OOSDeflationEngine


def _data_category(expression):
    """Dominant data category of an expression (by field-group membership)."""
    counts = {}
    for group, fields in config.FIELD_GROUPS.items():
        for field in fields:
            if re.search(rf"\b{re.escape(field)}\b", expression):
                counts[group] = counts.get(group, 0) + 1
    if not counts:
        return "other"
    return max(counts, key=counts.get)


async def _live_failed_checks(net, alpha_id):
    """Comma-joined names of is.checks BRAIN currently reports as FAIL for an
    alpha (PENDING submission-time checks are not failures). '' == BRAIN-clean or
    indeterminate. Fails OPEN on a network/parse error so a transient blip does
    not silently block an otherwise-qualified submission (the SQL gate already
    screened it)."""
    try:
        resp = await net.request("GET", f"/alphas/{alpha_id}")
        metrics = (resp.get("json") or {}).get("is") or {}
        checks = metrics.get("checks")
        if not isinstance(checks, list):
            return ""
        failed = []
        for c in checks:
            if isinstance(c, dict) and str(c.get("result", "")).upper() in ("FAIL", "ERROR"):
                name = str(c.get("name") or c.get("type") or "").strip().upper()
                if name:
                    failed.append(name)
        return ",".join(dict.fromkeys(failed))
    except Exception:
        return ""


def _diversified_order(candidates):
    """Greedy, diversity-aware ordering of submission candidates (Upgrade #7).

    Honors BRAIN's concentration guidance: cap any single data category's share
    of one run (SUBMISSION_MAX_CATEGORY_FRACTION) and skip alphas that are too
    structurally similar (AST motif) to ones already chosen, preferring a basket
    of marginally decorrelated alphas. Falls back to fitness order if the
    constraints would otherwise starve the run.
    """
    ranked = sorted(
        candidates,
        key=lambda c: c[4] if c[4] is not None else float("-inf"),
        reverse=True,
    )
    cap = config.MAX_SUBMISSIONS_PER_RUN
    max_per_cat = max(1, int(config.SUBMISSION_MAX_CATEGORY_FRACTION * cap))
    defl = OOSDeflationEngine()
    selected = []
    deferred = []
    cat_counts = {}
    for cand in ranked:
        expr = cand[0]
        cat = _data_category(expr)
        # Cross-universe variants of the SAME expression (the universe funnel)
        # are intentionally distinct, lightly-decorrelated submissions, so they
        # must NOT suppress one another via the structural-similarity filter --
        # otherwise every sweep variant but one is discarded after we already
        # paid the simulation cost (B8). Only compare against ALREADY-SELECTED
        # alphas with a DIFFERENT expression.
        other_exprs = [s[0] for s in selected if s[0] != expr]
        too_similar = bool(other_exprs) and defl.ast_similarity(
            expr, other_exprs
        ) >= config.SUBMISSION_MAX_SIMILARITY
        if cat_counts.get(cat, 0) >= max_per_cat or too_similar:
            deferred.append(cand)
            continue
        selected.append(cand)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if len(selected) >= cap:
            return selected
    for cand in deferred:  # backfill if diversity constraints under-filled the run
        if len(selected) >= cap:
            break
        selected.append(cand)
    return selected


async def submit():
    """Submit the best qualifying alphas to WorldQuant.

    Candidates are gated at the SQL level on the same criteria the orchestrator
    used to promote them: realized IS Sharpe >= MIN_SHARPE, MIN_TURNOVER <=
    turnover <= MAX_TURNOVER (BRAIN rejects sub-~1% turnover), and stored
    realized self-correlation <= MAX_SELF_CORRELATION.
    Ordered by fitness (deflated) so the most robust alphas go first, capped at
    MAX_SUBMISSIONS_PER_RUN.
    """
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

    net = NetworkEngine()
    submitted = 0
    try:
        for expr, alpha_id, sharpe, turnover, fitness, max_corr in _diversified_order(candidates):
            if submitted >= config.MAX_SUBMISSIONS_PER_RUN:
                print(f"Reached submission cap ({config.MAX_SUBMISSIONS_PER_RUN}).")
                break
            if not alpha_id or alpha_id == "MANUAL_SEED":
                continue
            # Final BRAIN-side guard: re-fetch is.checks live and SKIP any alpha
            # BRAIN currently flags (concentration, sub-universe Sharpe, turnover
            # floor, ...). Catches legacy rows promoted before the checks gate
            # existed (their stored failed_checks is NULL) and anything BRAIN has
            # re-evaluated since. Belt-and-suspenders over the SQL screen.
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
    asyncio.run(submit())