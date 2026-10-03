Part of **Forge v2 — Consultant Overhaul (Sept 2026)**. Offline validation harness — no network, no credentials: validates the catalog, per-axis vocabulary integrity (live operators only, balanced parens, availability pre-flight, loader-replica admission, compound verbatim passthrough, GROUP keys, template placeholders), bandit learning/persistence, pyramid boost, and ENB math. **Current status: 54 checks, 0 failed** against the real merged catalog (122,748 fields) and the real 84-operator live set (4 Sep 2026).
```python
"""Forge2 offline smoke test: validates the whole foundation against the REAL
merged catalog and the REAL live operator set -- no network, no credentials.

    python forge2_smoke_test.py --catalog brain_fields_merged.json \
        --operators-dir <snapshot>/detail/operators --outdir /tmp/forge2_smoke

Checks:
  1. catalog loads and axis availability is sane (USA/EUR x delay 0/1)
  2. vocabulary builds for three campaign axes; every emitted expression uses
     only LIVE operators, balances parentheses, respects axis availability
  3. loader-compat: a faithful replica of config._load_harvested_vocabulary
     admits >= 95% of emitted rows and passes compounds through verbatim
  4. seed pool templates: placeholders and GROUP-key wiring are valid
  5. bandit: priors, sampling, reward shift, persistence roundtrip
  6. pyramid resolver boosts multiplier-bearing expressions
  7. ENB math sanity (numpy permitting)
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import forge2_config as F2
from forge2_bandit import DatasetBandit
from forge2_catalog import CatalogIndex
from forge2_vocabulary import VocabularyBuilder, load_live_operators, ops_in

LEDGER = []


def check(name, ok, detail=""):
    LEDGER.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + detail) if detail else "")
    return ok


def paren_balanced(s):
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


ALLOWED_PLACEHOLDERS = {"NEUTRALIZATION", "LOOKBACK_SHORT", "LOOKBACK_LONG"}
_PLACEHOLDER_RE = re.compile(r"\{([A-Z_]+)\}")


def replica_loader(rows, max_fields=900, per_cat=300, max_alphas=5000):
    """Faithful replica of config._load_harvested_vocabulary (verbatim logic):
    which rows would the stock engine actually admit, and as what expression?"""
    rows = sorted(rows, key=lambda r: r.get("priorityScore", 0) or 0, reverse=True)
    field_exprs = []
    per_cat_count = Counter()
    seen = set()
    for r in rows:
        if len(field_exprs) >= max_fields:
            break
        fid = r.get("id")
        ftype = (r.get("type") or "").upper()
        if not fid or ftype not in ("MATRIX", "VECTOR"):
            continue
        if (r.get("alphaCount") or 0) > max_alphas:
            continue
        category = r.get("category")
        if per_cat_count[category] >= per_cat:
            continue
        expr = fid
        if ftype == "VECTOR":
            expr = "vec_avg(" + fid + ")"
        if r.get("coverageMode") == "backfill":
            expr = "ts_backfill(" + expr + ", 252)"
        if expr in seen:
            continue
        seen.add(expr)
        per_cat_count[category] += 1
        field_exprs.append(expr)
    return field_exprs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=F2.CATALOG_PATH)
    ap.add_argument("--operators", default=F2.OPERATORS_PATH)
    ap.add_argument("--operators-dir", default="")
    ap.add_argument("--outdir", default="/tmp/forge2_smoke")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 1 --- catalog ------------------------------------------------------------
    catalog = CatalogIndex(args.catalog)
    check("catalog loads >=100k fields", len(catalog.fields) >= 100000,
          str(len(catalog.fields)))
    axes = [("USA", 1), ("EUR", 1), ("USA", 0)]
    for region, delay in axes:
        stats = catalog.campaign_stats(region, delay)
        check("axis %s/d%d pool nonempty" % (region, delay), stats["pool"] > 1000,
              json.dumps(stats))

    live_ops = load_live_operators(args.operators, args.operators_dir)
    check("live operators loaded", len(live_ops) >= 60, str(len(live_ops)))
    for needed in ("vec_avg", "vec_stddev", "group_neutralize", "ts_backfill",
                   "subtract", "rank"):
        check("operator live: " + needed, needed in live_ops)

    # 2/3/4 --- vocabulary per axis ---------------------------------------------
    for region, delay in axes:
        builder = VocabularyBuilder(catalog, region, delay, live_ops, bandit=None)
        built = builder.write(outdir / (region + "_d" + str(delay)))
        rows = built["rows"]
        meta = built["meta"]
        seed_pool = built["seed_pool"]
        tag = "%s/d%d" % (region, delay)
        check(tag + " rows >= 300", len(rows) >= 300, str(len(rows)))
        check(tag + " classes", True, json.dumps(built["stats"]["classes"]))

        bad_ops, bad_paren, bad_avail, bad_compound = [], [], [], []
        for r in rows:
            rid = r["id"]
            if not paren_balanced(rid):
                bad_paren.append(rid)
            if live_ops and not (ops_in(rid) <= live_ops):
                bad_ops.append(rid)
            m = meta["fields"].get(rid) or {}
            if m.get("class") == "base":
                rec = catalog.fields.get(rid)
                if rec is None or not rec.available(region, delay):
                    bad_avail.append(rid)
            else:
                if r["type"] != "MATRIX" or r["coverageMode"] != "direct":
                    bad_compound.append(rid)
                for base in m.get("base") or []:
                    rec = catalog.fields.get(base)
                    if rec is None or not rec.available(region, delay):
                        bad_avail.append(rid)
        check(tag + " ops all live", not bad_ops, "; ".join(bad_ops[:3]))
        check(tag + " parens balanced", not bad_paren, "; ".join(bad_paren[:3]))
        check(tag + " availability preflight", not bad_avail,
              "; ".join(bad_avail[:3]))
        check(tag + " compounds MATRIX/direct", not bad_compound,
              "; ".join(bad_compound[:3]))

        admitted = replica_loader(rows)
        ratio = len(admitted) / max(1, len(rows))
        check(tag + " loader admits >=95%%", ratio >= 0.95,
              "%d/%d" % (len(admitted), len(rows)))
        compound_ids = [r["id"] for r in rows if "(" in r["id"]]
        passthrough = [e for e in admitted if e in set(compound_ids)]
        check(tag + " compounds pass through verbatim",
              len(passthrough) >= max(1, int(0.9 * len(compound_ids))),
              "%d/%d" % (len(passthrough), len(compound_ids)))

        gk = set(meta["group_keys"])
        check(tag + " group keys present", len(gk) >= 3, str(len(gk)))
        bad_gk = [g for g in gk
                  if catalog.fields.get(g) is None
                  or catalog.fields[g].type != "GROUP"
                  or catalog.fields[g].coverage < F2.GROUP_KEYS_MIN_COVERAGE]
        check(tag + " group keys valid", not bad_gk, "; ".join(bad_gk[:3]))

        bad_tmpl, uses_gk = [], 0
        for entry in seed_pool:
            for t in entry.get("templates") or []:
                if not paren_balanced(t):
                    bad_tmpl.append(t)
                    continue
                ph = set(_PLACEHOLDER_RE.findall(t))
                if not ph <= ALLOWED_PLACEHOLDERS:
                    bad_tmpl.append(t)
                    continue
                if live_ops and not (ops_in(t) <= live_ops):
                    bad_tmpl.append(t)
                    continue
                if any((" " + g + ")") in t for g in gk):
                    uses_gk += 1
        check(tag + " templates valid", not bad_tmpl, "; ".join(bad_tmpl[:2]))
        check(tag + " some templates use GROUP keys", uses_gk > 0, str(uses_gk))

    # 5 --- bandit ---------------------------------------------------------------
    bpath = outdir / "bandit_test.json"
    if bpath.exists():
        bpath.unlink()
    bandit = DatasetBandit(bpath)
    pool = catalog.signal_pool("USA", 1)
    datasets = list(dict.fromkeys(rec.dataset for _, rec in pool if rec.dataset))
    for ds in datasets[:200]:
        bandit.ensure_arm(ds, avg_multiplier=1.5, avg_alpha_count=10)
    sample = bandit.sample_arms(datasets[:200], 40)
    check("bandit samples 40 arms", len(sample) == 40, str(len(sample)))
    lucky = sample[0]
    for _ in range(30):
        bandit.update(lucky, True)
    for ds in sample[1:6]:
        for _ in range(30):
            bandit.update(ds, False)
    bandit.save()
    reloaded = DatasetBandit(bpath)
    mean_lucky = reloaded.arms[lucky]["a"] / (
        reloaded.arms[lucky]["a"] + reloaded.arms[lucky]["b"])
    mean_unlucky = reloaded.arms[sample[1]]["a"] / (
        reloaded.arms[sample[1]]["a"] + reloaded.arms[sample[1]]["b"])
    check("bandit learns + persists", mean_lucky > mean_unlucky,
          "%.3f > %.3f" % (mean_lucky, mean_unlucky))
    resample = Counter()
    for _ in range(200):
        for ds in reloaded.sample_arms(datasets[:200], 10):
            resample[ds] += 1
    check("bandit exploits winner", resample[lucky] >= resample.get(sample[1], 0),
          "%d vs %d" % (resample[lucky], resample.get(sample[1], 0)))

    # 6 --- pyramid resolver -------------------------------------------------------
    from forge2_factory import PyramidResolver
    meta_path = outdir / "USA_d1" / "forge2_field_meta.json"
    resolver = PyramidResolver(meta_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    rich = None
    for fid, m in meta["fields"].items():
        if m["class"] == "base" and m["multiplier"] >= 1.6:
            rich = (fid, m["multiplier"])
            break
    if rich:
        expr = "group_neutralize(rank(ts_zscore(" + rich[0] + ", 60)), INDUSTRY)"
        boost = resolver.boost(expr)
        expected = min(rich[1], F2.PYRAMID_BOOST_CAP) ** F2.PYRAMID_GAMMA
        check("pyramid boost applied", abs(boost - expected) < 1e-9,
              "%s -> %.3f (expected %.3f)" % (rich[0], boost, expected))
    else:
        check("pyramid boost applied", False, "no multiplier-bearing base field")
    check("pyramid boost neutral on unknown fields",
          resolver.boost("rank(close)") == 1.0)

    # 7 --- ENB sanity ---------------------------------------------------------------
    try:
        import numpy as np  # noqa
        from forge2_campaign import effective_number_of_bets
        dates = ["d%03d" % i for i in range(200)]
        import random as _r
        _r.seed(7)
        indep = {}
        for k in range(5):
            level, s = 0.0, {}
            for d in dates:
                level += _r.gauss(0, 1)
                s[d] = level
            indep["a" + str(k)] = s
        enb_i = effective_number_of_bets(indep, min_overlap=50)
        base = indep["a0"]
        dup = {"a": base, "b": dict(base), "c": dict(base)}
        enb_d = effective_number_of_bets(dup, min_overlap=50)
        check("ENB independent ~5", enb_i is not None and enb_i > 3.5,
              "%.2f" % (enb_i or -1))
        check("ENB duplicated ~1", enb_d is not None and enb_d < 1.5,
              "%.2f" % (enb_d or -1))
    except ImportError:
        check("ENB sanity (numpy missing; skipped)", True)

    # --- summary -------------------------------------------------------------------
    failures = [name for name, ok, _ in LEDGER if not ok]
    print("\n==== SMOKE SUMMARY: %d checks, %d failed ===="
          % (len(LEDGER), len(failures)))
    for name in failures:
        print("  FAILED:", name)
    summary = {
        "checks": len(LEDGER),
        "failed": failures,
    }
    (outdir / "smoke_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
```