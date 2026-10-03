"""submission_scout.py -- find & rank the genuinely submittable alphas.

Problem this solves: after ~7,000 simulations the handful of alphas that
(a) pass ALL of BRAIN's live is.checks, (b) clear the self-correlation
ceiling vs already-submitted alphas, and (c) are mutually decorrelated
with EACH OTHER are impossible to find by eye. This script:

  1. HARVESTS candidates from BOTH sources:
       * the local brain_memory.db population (anything with a real alpha_id
         and Sharpe >= MIN_SHARPE, turnover in band), AND
       * the live platform listing GET /users/self/alphas (status=UNSUBMITTED,
         ordered by -is.fitness) -- catching alphas simulated in runs whose
         local DB rows were lost or never enriched.
  2. DEEP-CHECKS each candidate LIVE:
       * GET /alphas/{id}            -> is.checks  (every PASS/FAIL gate BRAIN
                                        itself enforces at submission)
       * GET /alphas/{id}/correlations/self -> max PnL correlation vs your
                                        ALREADY-SUBMITTED (OS/ACTIVE) alphas
  3. RANKS survivors by fitness and greedily builds the SUBMISSION ORDER:
       pairwise PnL correlation (local alpha_pnl store, else fetched live)
       against the already-picked basket -- soft budget first
       (SUBMISSION_CORR_SOFT), then relaxed to the hard ceiling
       (SUBMISSION_CORR_HARD == platform rejection bar). This SIMULATES the
       sequential submission process: every pick tightens the constraint on
       the rest, which is exactly why only ~7-8 of many "passing" alphas
       are actually submittable before the correlation wall.
  4. REPORTS three tiers:
       TIER A  submit in this order (all checks PASS, self-corr OK, mutually
               decorrelated)
       TIER B  passes checks but correlated with a better Tier-A pick --
               becomes submittable only if you skip its rival
       TIER C  fails one or more live checks (named), or self-corr >= ceiling

Submits NOTHING. Feed Tier A to submit_to_worldquant.py when happy.
"""
import argparse
import asyncio
import math
import datetime

import config
from forge2_checks import parse_checks
from db_manager import DatabaseManager
from decorrelation_selector import _daily_returns, _pairwise_corr
from network_engine import NetworkEngine

# Alpha listing pagination.
LIST_PAGE_SIZE = 100
LIST_MAX_PAGES = 40          # up to 4,000 unsubmitted alphas scanned
# How many top-fitness candidates get the expensive live deep-check.
DEFAULT_DEEP_CHECK_TOP = 150
# Self-correlation / PnL recordsets are generated ASYNCHRONOUSLY by BRAIN
# (200 + empty body + Retry-After until ready) -- poll a few times.
RECORDSET_POLL_ATTEMPTS = 8


# --------------------------------------------------------------------------
# Harvest
# --------------------------------------------------------------------------
async def _list_platform_alphas(net):
    """All UNSUBMITTED alphas from the live platform, best fitness first.
    Returns {alpha_id: summary_dict}. Defensive: stops on first empty page."""
    found = {}
    for page in range(LIST_MAX_PAGES):
        offset = page * LIST_PAGE_SIZE
        resp = await net.request(
            "GET",
            f"/users/self/alphas?limit={LIST_PAGE_SIZE}&offset={offset}"
            f"&status=UNSUBMITTED&order=-is.fitness&hidden=false",
        )
        if resp.get("status_code") not in (200, 201):
            print(f"[scout] listing page {page}: HTTP {resp.get('status_code')}; stopping listing.")
            break
        body = resp.get("json") or {}
        results = body.get("results") or []
        if not results:
            break
        for a in results:
            aid = a.get("id")
            metrics = a.get("is") or {}
            if not aid:
                continue
            found[aid] = {
                "alpha_id": aid,
                "expression": ((a.get("regular") or {}).get("code")
                               if isinstance(a.get("regular"), dict) else None),
                "sharpe": metrics.get("sharpe"),
                "turnover": metrics.get("turnover"),
                "fitness": metrics.get("fitness"),
                "returns": metrics.get("returns"),
                "source": "platform",
            }
        if len(results) < LIST_PAGE_SIZE:
            break
    return found


def _local_candidates(db):
    """Local-DB rows with a real alpha_id worth deep-checking. Wider net than
    get_submission_candidates_sync ON PURPOSE: rows never enriched
    (is_qualified=0, max_correlation NULL) are exactly the 'lost' alphas the
    user cannot find -- the LIVE deep-check is the real gate here."""
    conn = db._sync_connection()
    cur = conn.execute(
        """
        SELECT expression, alpha_id, sharpe, turnover, fitness, returns
        FROM alpha_population
        WHERE alpha_id IS NOT NULL AND alpha_id != '' AND alpha_id != 'MANUAL_SEED'
          AND sharpe IS NOT NULL AND sharpe >= ?
          AND turnover IS NOT NULL AND turnover >= ? AND turnover <= ?
        ORDER BY COALESCE(fitness, 0) DESC
        """,
        (config.MIN_SHARPE, config.MIN_TURNOVER, config.MAX_TURNOVER),
    )
    out = {}
    for expr, aid, sharpe, turnover, fitness, returns in cur.fetchall():
        out[aid] = {
            "alpha_id": aid, "expression": expr, "sharpe": sharpe,
            "turnover": turnover, "fitness": fitness, "returns": returns,
            "source": "local_db",
        }
    return out


# --------------------------------------------------------------------------
# Live deep-checks
# --------------------------------------------------------------------------
async def _live_checks(net, alpha_id):
    """(failed_names, pending_names, metrics) from BRAIN's is.checks.
    failed_names None => could not determine (treat as BLOCKED, fail closed).
    SELF_CORRELATION PENDING is normal pre-submission and NOT a failure."""
    resp = await net.request("GET", f"/alphas/{alpha_id}")
    if resp.get("status_code") not in (200, 201):
        return None, None, {}
    body = resp.get("json") or {}
    metrics = body.get("is") or {}
    evidence = parse_checks(metrics)
    if not evidence.verified:
        return None, None, metrics
    return evidence.failed, evidence.pending, metrics


async def _poll_recordset(net, endpoint):
    """GET an async recordset, honoring BRAIN's empty-body-until-ready pattern."""
    for _ in range(RECORDSET_POLL_ATTEMPTS):
        resp = await net.request("GET", endpoint)
        if resp.get("status_code") not in (200, 201):
            return None
        body = resp.get("json")
        if body:  # ready
            return body
        # empty body + Retry-After (rate limiter already deferred) -> poll again
        await asyncio.sleep(2.0)
    return None


async def _self_correlation(net, alpha_id):
    """Max |PnL correlation| vs YOUR already-submitted alphas, or None when it
    could not be determined. Parses both known shapes: an explicit 'max' field,
    or histogram-style records whose first column is the correlation bucket."""
    body = await _poll_recordset(net, f"/alphas/{alpha_id}/correlations/self")
    if body is None:
        return None
    if isinstance(body, dict):
        if isinstance(body.get("max"), (int, float)):
            value=body["max"]
            return abs(float(value)) if not isinstance(value,bool) and math.isfinite(value) and abs(value)<=1 else None
        records = body.get("records")
        if isinstance(records, list) and records:
            vals = []
            for row in records:
                if isinstance(row, (list, tuple)) and row and isinstance(row[0], (int, float)):
                    if isinstance(row[0],bool) or not math.isfinite(row[0]) or abs(row[0])>1:return None
                    vals.append(abs(float(row[0])))
                elif isinstance(row, dict) and isinstance(row.get("correlation"), (int, float)):
                    value=row["correlation"]
                    if isinstance(value,bool) or not math.isfinite(value) or abs(value)>1:return None
                    vals.append(abs(float(value)))
                else:return None
            if vals:
                return max(vals)
        if isinstance(records, list) and not records:
            return 0.0  # no submitted alphas yet -> nothing to correlate with
    return None


async def _fetch_pnl(net, alpha_id):
    """[(date, cumulative_pnl)] from the platform, defensively parsed."""
    endpoint = config.WQ_PNL_ENDPOINT_TEMPLATE.format(alpha_id=alpha_id)
    body = await _poll_recordset(net, endpoint)
    if not isinstance(body, dict):
        return []
    records = body.get("records") or []
    series = []
    for row in records:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            d, p = row[0], row[-1]
        elif isinstance(row, dict):
            d, p = row.get("date"), row.get("pnl")
        else:
            continue
        if d is None or p is None:
            continue
        try:
            series.append((str(d)[:10], float(p)))
        except (TypeError, ValueError):
            continue
    return series


# --------------------------------------------------------------------------
# Greedy decorrelated ranking
# --------------------------------------------------------------------------
def _greedy_order(passing, returns_by_id):
    """Simulate the sequential submission process. Returns (tier_a, tier_b):
    tier_a = [(cand, worst_corr_at_admit)], the recommended submission order;
    tier_b = [(cand, blocking_corr, blocking_id)], passing-but-crowded-out."""
    ranked = sorted(passing, key=lambda c: c.get("consultant_value", c.get("fitness")) or 0.0, reverse=True)

    def worst_vs(cand, basket):
        r = returns_by_id.get(cand["alpha_id"])
        if r is None:
            return None, None
        worst, worst_id = 0.0, None
        for other, _ in basket:
            orets = returns_by_id.get(other["alpha_id"])
            if not orets:
                return None, other["alpha_id"]
            corr = _pairwise_corr(r, orets)
            if corr is None:
                return None, other["alpha_id"]
            if abs(corr) > worst:
                worst, worst_id = abs(corr), other["alpha_id"]
        return worst, worst_id

    tier_a, leftovers = [], []
    for budget in (config.SUBMISSION_CORR_SOFT, config.SUBMISSION_CORR_HARD):
        pool, leftovers = leftovers or ranked, []
        for cand in pool:
            if any(cand is c for c, _ in tier_a):
                continue
            w, wid = worst_vs(cand, tier_a)
            if w is None:
                leftovers.append(cand)      # no PnL -> decide in the last pass
            elif w <= budget:
                tier_a.append((cand, w))
            else:
                leftovers.append(cand)
    tier_b = []
    for cand in leftovers:
        w, wid = worst_vs(cand, tier_a)
        if w is None:
            tier_b.append((cand,None,"PNL_UNVERIFIABLE"))     # correlation UNVERIFIED, flagged in report
        else:
            tier_b.append((cand, w, wid))
    return tier_a, tier_b


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
async def scout(top_n, local_only=False, refresh_corr=False):
    db = DatabaseManager()
    db.init_db_sync()
    net = NetworkEngine()
    try:
        candidates = _local_candidates(db)
        print(f"[scout] local DB candidates with alpha_id in gate band: {len(candidates)}")
        if not local_only:
            platform = await _list_platform_alphas(net)
            print(f"[scout] live platform UNSUBMITTED alphas listed: {len(platform)}")
            for aid, summary in platform.items():
                candidates.setdefault(aid, summary)   # local metadata wins
        ranked = sorted(candidates.values(), key=lambda c: c.get("consultant_value", c.get("fitness")) or 0.0, reverse=True)
        deep = ranked[:top_n]
        print(f"[scout] deep-checking top {len(deep)} of {len(ranked)} by fitness...")

        passing, tier_c = [], []
        for i, cand in enumerate(deep, 1):
            aid = cand["alpha_id"]
            failed, pending, metrics = await _live_checks(net, aid)
            # Prefer LIVE metrics over stale local rows.
            for key in ("sharpe", "turnover", "fitness", "returns"):
                if isinstance(metrics.get(key), (int, float)):
                    cand[key] = metrics[key]
            evidence=parse_checks(metrics)
            cand["raw_checks"]=evidence.raw
            cand["sharpe_2y"]=evidence.sharpe_2y
            cand["pnl_realization"]=evidence.pnl_realization
            cand["pyramid_multiplier"]=evidence.pyramid_multiplier
            cand["warnings"]=evidence.warnings
            cand["unknown_checks"]=evidence.unknown
            cand["consultant_value"]=(cand.get("fitness") or 0.0)*(evidence.pyramid_multiplier or 1.0)
            if failed is None:
                tier_c.append((cand, "CHECKS_UNVERIFIABLE (network/parse; fail closed)"))
                continue
            if failed:
                tier_c.append((cand, "FAILED: " + ",".join(failed)))
                continue
            corr = await _self_correlation(net, aid) if refresh_corr or True else None
            cand["self_corr"] = corr
            cand["pending"] = pending
            if corr is None:
                tier_c.append((cand,"SELF_CORRELATION_UNVERIFIABLE"))
                continue
            if corr > config.MAX_SELF_CORRELATION:
                tier_c.append((cand, f"SELF_CORRELATION {corr:.3f} > {config.MAX_SELF_CORRELATION}"))
                continue
            passing.append(cand)
            print(f"  [{i}/{len(deep)}] PASS {aid} sharpe={cand.get('sharpe')} "
                  f"fitness={cand.get('fitness')} self_corr={corr}")

        # Pairwise PnL: local store first, fetch (and persist) the gaps.
        returns_by_id = {}
        for cand in passing:
            aid = cand["alpha_id"]
            rows = db.load_pnl_sync(aid)
            if not rows:
                series = await _fetch_pnl(net, aid)
                if series:
                    db.save_pnl_sync(aid, series)
                    rows = series
            if rows:
                returns_by_id[aid] = _daily_returns(rows)

        passing.sort(key=lambda c:c.get("consultant_value",0),reverse=True)
        tier_a, tier_b = _greedy_order(passing, returns_by_id)
        from forge2_storage import atomic_json
        atomic_json("submission_scout_evidence.json", {"passing":passing,
                    "blocked":[{"candidate":c,"reason":reason} for c,reason in tier_c]})
        _report(tier_a, tier_b, tier_c, len(ranked), len(deep))
    finally:
        await net.close()
        db.close_sync()


def _fmt(x, spec=".3f"):
    return format(x, spec) if isinstance(x, (int, float)) else "n/a"


def _report(tier_a, tier_b, tier_c, total, checked):
    lines = [f"# Submission Scout Report -- {datetime.datetime.now():%Y-%m-%d %H:%M}",
             f"\nScanned {total} candidates, deep-checked top {checked}.\n",
             "## TIER A -- submit in this order (all live checks PASS, decorrelated)\n"]
    for i, (c, w) in enumerate(tier_a, 1):
        corr_txt = "UNVERIFIED (no PnL)" if w is None else f"{w:.3f}"
        lines.append(
            f"{i:2d}. `{c['alpha_id']}` fitness={_fmt(c.get('fitness'))} "
            f"sharpe={_fmt(c.get('sharpe'))} turnover={_fmt(c.get('turnover'))} "
            f"self_corr={_fmt(c.get('self_corr'))} basket_corr={corr_txt} "
            f"2Y_sharpe={_fmt(c.get('sharpe_2y'))} realization={_fmt(c.get('pnl_realization'))} "
            f"pyramid={_fmt(c.get('pyramid_multiplier'))} value_proxy={_fmt(c.get('consultant_value'))}")
        if c.get("expression"):
            lines.append(f"      `{c['expression']}`")
    lines.append("\n## TIER B -- pass checks but crowded out by a Tier-A pick\n")
    for c, w, wid in sorted(tier_b, key=lambda t: t[0].get("fitness") or 0, reverse=True):
        lines.append(f"- `{c['alpha_id']}` fitness={_fmt(c.get('fitness'))} "
                     f"blocked by `{wid}` at |corr|={_fmt(w)}")
    lines.append("\n## TIER C -- currently NOT submittable (live reason)\n")
    for c, reason in sorted(tier_c, key=lambda t: t[0].get("fitness") or 0, reverse=True):
        lines.append(f"- `{c['alpha_id']}` fitness={_fmt(c.get('fitness'))} -> {reason}")
    text = "\n".join(lines)
    print("\n" + text)
    with open("submission_scout_report.md", "w", encoding="utf-8") as fh:
        fh.write(text)
    print("\n[scout] wrote submission_scout_report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find & rank submittable alphas (read-only).")
    ap.add_argument("--top", type=int, default=DEFAULT_DEEP_CHECK_TOP,
                    help="deep-check only the top N candidates by fitness")
    ap.add_argument("--local-only", action="store_true",
                    help="skip the live /users/self/alphas listing")
    ap.add_argument("--refresh-corr", action="store_true",
                    help="force re-fetch of self-correlation for every candidate")
    args = ap.parse_args()
    asyncio.run(scout(args.top, local_only=args.local_only, refresh_corr=args.refresh_corr))
