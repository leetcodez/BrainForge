"""Harvest the full WorldQuant BRAIN data-field catalog, score every field by
the data-first PriorityScore, and write a ranked data_fields.json plus a
diversified seed_pool.json.

Run AFTER probe_wq.py confirms connectivity:

    python field_harvester.py

Read-only against BRAIN (GET only). Writes data_fields.json (full ranked
catalog) and seed_pool.json (diversified per-category shortlist) next to this
file. It never invents fields; every row comes straight from the live API.

Design notes (v2):
  * Model fields are PRE-COMPUTED factor outputs, not raw data. A simple
    transform on them adds little and tends to be correlated, so the Model
    category is DOWN-WEIGHTED (CATEGORY_MULTIPLIER).
  * Crowding uses a SWEET-SPOT curve, not \"lower is always better\": a field
    with ~1 alpha is unproven, not gold; the score peaks for low-but-validated
    fields and decays for crowded ones.
  * Low coverage is no longer an instant disqualifier. Event/sentiment data is
    naturally sparse; such fields are tagged coverageMode=\"backfill\" so the
    seeder can wrap them in ts_backfill(...). Backfill fixes TEMPORAL sparsity
    (stale-but-valid values between events), NOT cross-sectional gaps where
    only some names ever have data.
  * Selection uses PER-CATEGORY QUOTAS so the seed pool is diversified across
    data families, which is what the pyramid / Triple-Axis Plan rewards.
"""
import asyncio
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode

import config
from network_engine import NetworkEngine

CATALOG_PATH = Path(__file__).with_name("data_fields.json")
SEED_POOL_PATH = Path(__file__).with_name("seed_pool.json")

# --- PriorityScore knobs (override in config.py to retune) -----------------
WEIGHTS = {
    "value": getattr(config, "FIELD_W_VALUE", 0.30),
    "maturity": getattr(config, "FIELD_W_MATURITY", 0.25),
    "coverage": getattr(config, "FIELD_W_COVERAGE", 0.20),
    "history": getattr(config, "FIELD_W_HISTORY", 0.15),
    "simplicity": getattr(config, "FIELD_W_SIMPLICITY", 0.10),
}
MIN_COVERAGE_FLOOR = getattr(config, "FIELD_MIN_COVERAGE_FLOOR", 0.05)
HIGH_COVERAGE = getattr(config, "FIELD_HIGH_COVERAGE", 0.60)
PROVEN_FULL_AT = getattr(config, "FIELD_PROVEN_FULL_AT", 5)
# When scoping to ONE niche dataset (WQ_DATASET_ID set) every field is the same
# category, so a small per-category quota would throttle the seed pool to ~30
# fields and re-introduce seed starvation. Open the quota wide in that mode so
# the whole curated dataset can seed; keep the tight default for full-catalog runs.
_RESTRICTED = bool(getattr(config, "WQ_DATASET_ID", ""))
PER_CATEGORY_QUOTA = getattr(config, "FIELD_PER_CATEGORY_QUOTA", 500 if _RESTRICTED else 30)
# Keep zero-alpha (never-used) fields? On the FULL catalog a field nobody has
# ever built an alpha on is usually unproven noise, so it is dropped. But the
# whole point of scoping to a niche dataset is to PIONEER its uncrowded fields --
# there, zero existing alphas is precisely the signal we want, not a reason to
# skip. So in a restricted run we KEEP them by default and author the first alpha
# on them. Override either way via config.FIELD_KEEP_ZERO_ALPHA.
KEEP_ZERO_ALPHA = getattr(config, "FIELD_KEEP_ZERO_ALPHA", _RESTRICTED)
SIMPLICITY_BY_TYPE = {"MATRIX": 1.0, "VECTOR": 0.4, "GROUP": 0.0}
# Composite model outputs are pre-derived signals -> down-weight (corr risk).
CATEGORY_MULTIPLIER = {"Model": getattr(config, "FIELD_W_MODEL", 0.6)}
PAGE_SIZE = 50

# --- Crowding penalty (Upgrade B) ------------------------------------------
# The sweet-spot maturity term alone let high-valueScore but heavily-crowded
# fields (thousands of existing alphas) out-rank uncrowded ones. This explicit
# multiplicative dampener pushes crowded fields down so the "attack uncrowded
# data" thesis actually holds. crowd in [0,1] blends alpha- and user-count.
CROWD_PENALTY = getattr(config, "FIELD_CROWDING_PENALTY", 0.6)
CROWD_FLOOR = getattr(config, "FIELD_CROWDING_FLOOR", 0.25)

# --- Category-aware template families (Upgrade A) --------------------------
# Field-id / category stems used to route each field to a tailored template
# family instead of one monotone archetype set.
_OPTIONS_STEMS = tuple(getattr(config, "FAMILY_OPTIONS_STEMS",
                  ("atmiv", "exerniv", "_iv", "div", "clshv", "orhv", "straddle",
                   "strap", "ernmv", "impernmv", "slope", "erneff", "dtex", "ern4_")))
_ANALYST_STEMS = tuple(getattr(config, "FAMILY_ANALYST_STEMS",
                  ("guidance", "estimate", "consensus", "eps", "ebitda", "sales",
                   "netprofit", "cfo", "fcf", "capex", "bookvalue", "revision")))
_SENTIMENT_STEMS = tuple(getattr(config, "FAMILY_SENTIMENT_STEMS",
                  ("sentiment", "snt1", "snt_", "news", "social", "buzz", "mood",
                   "focusrank", "stockrank", "torpedo")))
MAX_SPREAD_TEMPLATES = getattr(config, "SEED_MAX_SPREAD_TEMPLATES", 2)
_NUM_RE = re.compile(r"\d+")

# --- Seed-pool filters (STRICTER than the full catalog) ---------------------
# The seed pool is what actually seeds the generator, so it is curated harder
# than the ranked catalog: drop pre-derived Model composites, crowded fields,
# mechanical/non-signal plumbing, and non-usable types. Each surviving field
# gets ready-to-fill simple templates (one alpha per field = breadth-first).
SEED_EXCLUDE_CATEGORIES = set(getattr(config, "SEED_EXCLUDE_CATEGORIES", ["Model"]))
SEED_EXCLUDE_TYPES = set(getattr(config, "SEED_EXCLUDE_TYPES", ["GROUP"]))
SEED_MAX_ALPHAS = getattr(config, "SEED_MAX_ALPHAS", 200)
SEED_DENYLIST = [s.lower() for s in getattr(config, "SEED_DENYLIST", [
    "adjfactor", "splitfactor", "currency", "fx_rate", "shares_out",
])]


def _base_params():
    return {
        "instrumentType": config.DEFAULT_INSTRUMENT,
        "region": config.DEFAULT_REGION,
        "delay": config.DEFAULT_DELAY,
        "universe": config.UNIVERSES[0],
    }


async def _fetch_all(net, endpoint, extra=None):
    """Page through an offset-paginated BRAIN list endpoint; return all rows."""
    params = _base_params()
    if extra:
        params.update(extra)
    rows = []
    offset = 0
    total = None
    while True:
        page_params = {**params, "limit": PAGE_SIZE, "offset": offset}
        res = await net.request("GET", f"{endpoint}?{urlencode(page_params)}")
        if res["status_code"] != 200 or not isinstance(res["json"], dict):
            print(f"  WARN {endpoint} offset={offset} -> HTTP {res['status_code']}; stopping early.")
            break
        body = res["json"]
        if total is None:
            total = body.get("count")
            print(f"  {endpoint}: count={total}")
        page = body.get("results") or []
        if not page:
            break
        rows.extend(page)
        offset += PAGE_SIZE
        if total is not None and offset >= total:
            break
    print(f"  {endpoint}: fetched {len(rows)} row(s).")
    return rows


def _dataset_id(field):
    ds = field.get("dataset")
    if isinstance(ds, dict):
        return ds.get("id")
    return field.get("dataset.id") or field.get("datasetId") or ds


def _category_name(obj):
    cat = obj.get("category") if isinstance(obj, dict) else None
    if isinstance(cat, dict):
        return cat.get("name") or cat.get("id")
    return cat


def _minmax(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return (0.0, 1.0)
    lo, hi = min(vals), max(vals)
    return (lo, hi if hi > lo else lo + 1.0)


def _norm(v, lo, hi):
    if not isinstance(v, (int, float)):
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _maturity(alpha_count, crowd_lo, crowd_hi):
    """Sweet-spot crowding score: penalizes BOTH unproven (~1 alpha) and
    crowded (very high) fields, peaking for low-but-validated fields.
        proven    : 0 -> 1 as alpha_count rises to PROVEN_FULL_AT
        uncrowded : 1 -> 0 as alpha_count grows (inverse, log-scaled)
    """
    proven = min(1.0, alpha_count / PROVEN_FULL_AT) if PROVEN_FULL_AT > 0 else 1.0
    uncrowded = 1.0 - _norm(math.log1p(alpha_count), crowd_lo, crowd_hi)
    return proven * uncrowded


def _seedable(row):
    """Seed-pool gate (stricter than scoring): no Model composites, no crowded
    fields, no mechanical plumbing, no non-usable types."""
    if row["category"] in SEED_EXCLUDE_CATEGORIES:
        return False
    if row["type"] in SEED_EXCLUDE_TYPES:
        return False
    if (row["alphaCount"] or 0) > SEED_MAX_ALPHAS:
        return False
    fid = (row["id"] or "").lower()
    return not any(bad in fid for bad in SEED_DENYLIST)


def _family_of(field_id, category):
    """Route a field to a template family from its id/category stems."""
    fid = (field_id or "").lower()
    cat = (category or "").lower()
    if any(s in fid for s in _OPTIONS_STEMS) or "option" in cat or "volatil" in cat:
        return "options_vol"
    if (any(s in fid for s in _ANALYST_STEMS) or "analyst" in cat
            or "fundamental" in cat or "estimate" in cat):
        return "analyst"
    if (any(s in fid for s in _SENTIMENT_STEMS) or "sentiment" in cat
            or "news" in cat or "social" in cat):
        return "sentiment"
    return "default"


def _term_key(field_id):
    """Split a field id around its LAST numeric token so siblings that differ
    only by a term index (m1atmiv vs m2atmiv, ernmv1 vs ernmv12) share a stem.
    Returns (stem_with_placeholder, index) or (None, None)."""
    matches = list(_NUM_RE.finditer(field_id or ""))
    if not matches:
        return None, None
    m = matches[-1]
    try:
        idx = int(m.group())
    except ValueError:
        return None, None
    stem = field_id[:m.start()] + "#N#" + field_id[m.end():]
    return stem, idx


def _field_operand(row):
    """Field expression used as a spread operand (vec_avg / ts_backfill wrapped
    exactly like the single-field templates)."""
    expr = row["id"]
    if row["type"] == "VECTOR":
        expr = "vec_avg(" + expr + ")"
    if row["coverageMode"] == "backfill":
        # Fixed ~1y backfill window (config.HARVEST_BACKFILL_WINDOW), NOT the
        # {LOOKBACK_LONG} smoothing placeholder: densification (carry the value
        # across quarterly events) must be decoupled from the smoothing window so
        # a long backfill never drags the smoother long too and crushes turnover.
        expr = "ts_backfill(" + expr + ", " + str(getattr(config, "HARVEST_BACKFILL_WINDOW", 252)) + ")"
    return expr


def _crowding_multiplier(alpha_count, user_count, crowd_lo, crowd_hi, user_lo, user_hi):
    """Upgrade B: multiplicative dampener in [CROWD_FLOOR, 1]. 1.0 for an
    uncrowded field, shrinking toward CROWD_FLOOR as alpha/user counts rise."""
    a = _norm(math.log1p(alpha_count or 0), crowd_lo, crowd_hi)
    u = _norm(math.log1p(user_count or 0), user_lo, user_hi)
    crowd = max(a, u)
    return max(CROWD_FLOOR, 1.0 - CROWD_PENALTY * crowd)


def _seed_templates(field_id, ftype, mode, category):
    """Build ready-to-fill templates for one field, tailored to its data family
    (Upgrade A) and branching on type/sparsity. VECTOR fields are collapsed with
    vec_avg; sparse (backfill) fields are wrapped in ts_backfill so the signal
    persists between events. {NEUTRALIZATION}/{LOOKBACK_*} are left for the seed
    generator to fill.
        options_vol : level + vol-regime z-score + short-horizon change +
                      mean-reversion vs own average (term-structure dynamics).
        analyst     : level + short/long REVISION (ts_delta of consensus) +
                      normalized level (dispersion/revision signals).
        sentiment   : CROWDED -> only the two least-crowded forms (regime
                      z-score + change) so we do not flood a saturated family.
        default     : the original four archetypes."""
    expr = field_id
    if ftype == "VECTOR":
        expr = "vec_avg(" + expr + ")"
    if mode == "backfill":
        # Fixed ~1y backfill (config.HARVEST_BACKFILL_WINDOW) decoupled from the
        # {LOOKBACK_*} smoothing windows: carry the sparse value across events
        # for breadth WITHOUT forcing the smoother long (which kills turnover).
        expr = "ts_backfill(" + expr + ", " + str(getattr(config, "HARVEST_BACKFILL_WINDOW", 252)) + ")"
    family = _family_of(field_id, category)
    if family == "options_vol":
        return [
            "group_neutralize(rank(" + expr + "), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_zscore(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_delta(" + expr + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
            "group_neutralize(-rank(ts_av_diff(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
        ]
    if family == "analyst":
        return [
            "group_neutralize(rank(" + expr + "), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_delta(" + expr + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_delta(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_zscore(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
        ]
    if family == "sentiment":
        return [
            "group_neutralize(rank(ts_zscore(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_delta(" + expr + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
        ]
    return [
        "group_neutralize(rank(" + expr + "), {NEUTRALIZATION})",
        "group_neutralize(-rank(" + expr + "), {NEUTRALIZATION})",
        # Non-rank shapes so the default family does not seed a pure
        # group_neutralize(rank(...)) monoculture (the selection-time skeleton
        # cap then keeps it diverse downstream).
        "group_neutralize(ts_zscore(" + expr + ", {LOOKBACK_LONG}), {NEUTRALIZATION})",
        "group_neutralize(ts_decay_linear(ts_delta(" + expr + ", {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
        "group_neutralize(sign(ts_delta(" + expr + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
    ]


_SEMANTIC_PAIRS = tuple(getattr(config, "SEED_SEMANTIC_PAIRS", (
    ("call", "put"), ("calls", "puts"), ("bid", "ask"), ("long", "short"),
    ("buy", "sell"), ("bull", "bear"), ("inflow", "outflow"),
    ("upgrade", "downgrade"),
)))
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _semantic_pair_key(field_id):
    """If field_id contains exactly one half of a known semantic pair (call/put,
    bid/ask, long/short, ...), return (stem_with_placeholder, side 0|1) so its
    complement shares a stem. side orders the spread (0 minus 1). Returns
    (None, None) when zero or more-than-one pair tokens are present."""
    fid = (field_id or "").lower()
    tokens = {t for t in _TOKEN_SPLIT_RE.split(fid) if t}
    found = None
    for a, b in _SEMANTIC_PAIRS:
        a_in, b_in = a in tokens, b in tokens
        if a_in == b_in:
            continue
        cand = (a, b, 0 if a_in else 1)
        if found is not None:
            return None, None
        found = cand
    if not found:
        return None, None
    a, b, side = found
    present = a if side == 0 else b
    stem = re.sub(rf"(?<![a-z0-9]){re.escape(present)}(?![a-z0-9])", "#P#", fid, count=1)
    return stem, side


def _attach_curve_spread_seeds(seed_pool, scored, max_total=None):
    """Seed PAIRED-DATA spreads -- term-structure curves (near minus far of one
    family) and complementary skews (call vs put, bid vs ask) -- scanning the
    FULL catalog, including fields excluded from single-field seeding (notably
    pre-derived Model composites such as the mdl53 default-probability curve). A
    lone Model field is crowded and correlated, but a curve-steepness or skew
    spread built from two of them is a distinct, less-crowded signal worth
    seeding. Capped by SEED_CURVE_SPREAD_MAX."""
    cap = max_total if max_total is not None else int(getattr(config, "SEED_CURVE_SPREAD_MAX", 40))
    if cap <= 0:
        return
    existing = {r["id"] for r in seed_pool}
    term_groups = defaultdict(list)
    sem_groups = defaultdict(dict)
    for r in scored:
        ds = r.get("dataset")
        stem, idx = _term_key(r["id"])
        if stem is not None:
            term_groups[(ds, stem)].append((idx, r))
        s_stem, side = _semantic_pair_key(r["id"])
        if s_stem is not None:
            sem_groups[(ds, s_stem)].setdefault(side, r)
    new_entries = {}
    added = 0

    def _emit(row_lo, row_hi, kind):
        nonlocal added
        if added >= cap:
            return
        diff = "subtract(" + _field_operand(row_lo) + ", " + _field_operand(row_hi) + ")"
        tmpls = [
            "group_neutralize(rank(" + diff + "), {NEUTRALIZATION})",
            "group_neutralize(rank(ts_delta(" + diff + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
        ]
        host = row_lo["id"]
        if host in existing:
            for r in seed_pool:
                if r["id"] == host:
                    r.setdefault("templates", []).extend(tmpls)
                    break
        else:
            entry = new_entries.get(host)
            if entry is None:
                entry = {**row_lo, "templates": [], "seedReason": kind}
                new_entries[host] = entry
            entry["templates"].extend(tmpls)
        added += 1

    for members in term_groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda t: t[0])
        for (_, row_a), (_, row_b) in zip(members, members[1:]):
            _emit(row_a, row_b, "term-structure")
    for sides in sem_groups.values():
        if 0 in sides and 1 in sides:
            _emit(sides[0], sides[1], "semantic-pair")
    if new_entries:
        seed_pool.extend(new_entries.values())


def _attach_spread_templates(seed_pool):
    """Upgrade A: term-structure / cross-field spreads. For structured fields
    that have a same-dataset sibling differing only by a term index (e.g.
    m1atmiv vs m2atmiv, ernmv1 vs ernmv2) add a near-minus-far spread seed --
    a signal no single-field template can express. Crowded sentiment families
    are skipped; at most MAX_SPREAD_TEMPLATES spreads are added per field."""
    groups = defaultdict(list)
    for r in seed_pool:
        if _family_of(r["id"], r["category"]) not in ("options_vol", "analyst"):
            continue
        stem, idx = _term_key(r["id"])
        if stem is None:
            continue
        groups[(r["dataset"], stem)].append((idx, r))
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda t: t[0])
        added = 0
        for (idx_a, row_a), (idx_b, row_b) in zip(members, members[1:]):
            if added >= MAX_SPREAD_TEMPLATES:
                break
            spread = ("group_neutralize(rank(subtract(" + _field_operand(row_a)
                      + ", " + _field_operand(row_b) + ")), {NEUTRALIZATION})")
            row_a.setdefault("templates", []).append(spread)
            added += 1


async def main():
    net = NetworkEngine()
    try:
        print("Harvesting data-sets (value score + history live here)...")
        datasets = await _fetch_all(net, "/data-sets")
        ds_by_id = {d.get("id"): d for d in datasets if d.get("id")}

        ds_filter = getattr(config, "WQ_DATASET_ID", "")
        if ds_filter:
            print(f"Harvesting data-fields (dataset-scoped: {ds_filter})...")
            fields = await _fetch_all(net, "/data-fields", {"dataset.id": ds_filter})
        else:
            print("Harvesting data-fields (full catalog)...")
            fields = await _fetch_all(net, "/data-fields")
        if not fields:
            print("No fields returned -- check auth / params. Aborting.")
            return

        # Value score & history come from the parent dataset; normalize across that.
        value_lo, value_hi = _minmax(
            [ds_by_id.get(_dataset_id(f), {}).get("valueScore") for f in fields]
        )
        crowd_lo, crowd_hi = _minmax([math.log1p(f.get("alphaCount") or 0) for f in fields])
        user_lo, user_hi = _minmax([math.log1p(f.get("userCount") or 0) for f in fields])

        scored = []
        dropped = {"dead_coverage": 0, "zero_alpha": 0, "bad_type": 0}
        for f in fields:
            cov = f.get("coverage")
            alpha_count = f.get("alphaCount") or 0
            ftype = (f.get("type") or "").upper()
            # Hard filters: keep sparse (event) fields, drop only truly dead ones.
            if not isinstance(cov, (int, float)) or cov < MIN_COVERAGE_FLOOR:
                dropped["dead_coverage"] += 1
                continue
            if alpha_count <= 0 and not KEEP_ZERO_ALPHA:
                dropped["zero_alpha"] += 1
                continue
            if ftype not in SIMPLICITY_BY_TYPE:
                dropped["bad_type"] += 1
                continue

            ds = ds_by_id.get(_dataset_id(f), {})
            category = _category_name(ds) or _category_name(f)
            value = _norm(ds.get("valueScore"), value_lo, value_hi)
            maturity = _maturity(alpha_count, crowd_lo, crowd_hi)
            coverage = max(0.0, min(1.0, cov))
            history = ds.get("dateCoverage")
            history = max(0.0, min(1.0, history)) if isinstance(history, (int, float)) else 0.0
            simplicity = SIMPLICITY_BY_TYPE[ftype]

            score = (
                WEIGHTS["value"] * value
                + WEIGHTS["maturity"] * maturity
                + WEIGHTS["coverage"] * coverage
                + WEIGHTS["history"] * history
                + WEIGHTS["simplicity"] * simplicity
            )
            score *= CATEGORY_MULTIPLIER.get(category, 1.0)
            # Upgrade B: explicitly down-rank crowded fields (alpha/user count).
            score *= _crowding_multiplier(alpha_count, f.get("userCount") or 0,
                                          crowd_lo, crowd_hi, user_lo, user_hi)

            scored.append({
                "id": f.get("id"),
                "description": f.get("description"),
                "type": ftype,
                "dataset": _dataset_id(f),
                "category": category,
                "coverage": round(coverage, 4),
                "coverageMode": "direct" if cov >= HIGH_COVERAGE else "backfill",
                "dateCoverage": round(history, 4),
                "alphaCount": alpha_count,
                "userCount": f.get("userCount"),
                "valueScore": ds.get("valueScore"),
                "priorityScore": round(score, 4),
            })

        scored.sort(key=lambda r: r["priorityScore"], reverse=True)
        CATALOG_PATH.write_text(json.dumps(scored, indent=2), encoding="utf-8")

        # Diversified seed pool: curate harder than the catalog, then take the
        # top PER_CATEGORY_QUOTA per category and attach ready seed templates.
        seed_candidates = [r for r in scored if _seedable(r)]
        by_cat_rows = defaultdict(list)
        for r in seed_candidates:
            by_cat_rows[r["category"]].append(r)
        seed_pool = []
        for cat, rows in by_cat_rows.items():
            seed_pool.extend(rows[:PER_CATEGORY_QUOTA])
        seed_pool.sort(key=lambda r: r["priorityScore"], reverse=True)
        for r in seed_pool:
            r["templates"] = _seed_templates(r["id"], r["type"], r["coverageMode"], r["category"])
        # Upgrade A: add term-structure / cross-field spread seeds where siblings exist.
        _attach_spread_templates(seed_pool)
        # Paired-data spreads (call/put skew, default-probability curve, ...),
        # incl. fields excluded from single-field seeding (e.g. Model composites).
        _attach_curve_spread_seeds(seed_pool, scored)
        SEED_POOL_PATH.write_text(json.dumps(seed_pool, indent=2), encoding="utf-8")

        print(f"\nScored {len(scored)} field(s); dropped "
              f"{dropped['dead_coverage']} dead-coverage, "
              f"{dropped['zero_alpha']} zero-alpha, {dropped['bad_type']} bad-type.")
        print(f"Wrote full ranked catalog -> {CATALOG_PATH.name}")
        print(f"Wrote diversified seed pool ({len(seed_pool)} fields, "
              f"{sum(len(r['templates']) for r in seed_pool)} templates) -> {SEED_POOL_PATH.name}")
        print(f"  (seed pool excludes {sorted(SEED_EXCLUDE_CATEGORIES)}, "
              f"types {sorted(SEED_EXCLUDE_TYPES)}, alphas>{SEED_MAX_ALPHAS}, and mechanical fields)")

        direct = sum(1 for r in scored if r["coverageMode"] == "direct")
        print(f"\nCoverage modes: {direct} direct, {len(scored) - direct} need ts_backfill (sparse/event).")

        by_cat = Counter(r["category"] for r in scored)
        print("\nQualified fields by category:")
        for cat, n in by_cat.most_common():
            print(f"  {cat or '(uncategorized)'}: {n}")

        print("\nDiversified seed pool -- top 3 per category:")
        shown = defaultdict(int)
        for r in seed_pool:
            if shown[r["category"]] >= 3:
                continue
            shown[r["category"]] += 1
            print(f"  {r['priorityScore']:.3f}  {str(r['id'])[:38]:<38} "
                  f"cov={r['coverage']:.2f}({r['coverageMode'][:1]}) "
                  f"alphas={str(r['alphaCount']):<6} {r['type']:<6} [{r['category']}]")
    finally:
        await net.close()


if __name__ == "__main__":
    asyncio.run(main())
