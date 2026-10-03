"""Forge2 catalog index: offline view of the full BRAIN field catalog.

Loads the merged snapshot catalog (122,748 fields) and exposes:
  * availability(region, delay)  -- offline PRE-FLIGHT so no simulation is ever
    wasted on a field that does not exist on the campaign's axes (finding #3);
  * consultant priority scoring  -- pyramid-multiplier-aware, crowding-damped
    (findings #2, #13);
  * semantic structure           -- dataset neighborhoods, term-structure
    families, semantic pairs (finding #11);
  * GROUP neutralization keys    -- per-region grouping fields (finding #6).

Stdlib-only and read-only: this module never talks to the network.
"""

import hashlib
import copy
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import forge2_config as F2

_NUM_RE = re.compile(r"\d+")
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

# Semantic complement tokens (long/short style pairs) for spread candidates.
SEMANTIC_PAIRS = (
    ("call", "put"), ("calls", "puts"), ("bid", "ask"), ("long", "short"),
    ("buy", "sell"), ("bull", "bear"), ("inflow", "outflow"),
    ("upgrade", "downgrade"), ("positive", "negative"), ("up", "down"),
)

# Keyword routing for template families (kept consistent with repo config).
_FAMILY_KEYWORDS = [
    ("earnings_event", ("announcement", "post earnings", "post-earnings",
                        "earnings move", "percent move", "pct move", "ernmv",
                        "next earnings", "earnings reaction", "earnings date")),
    ("options_vol", ("implied vol", "implied", "option", "open interest",
                     "skew", "straddle", "volatilit", "vega", "atm",
                     "term structure")),
    ("analyst", ("estimate", "consensus", "guidance", "eps", "ebitda",
                 "revenue", "forecast", "recommendation", "target price",
                 "revision", "analyst")),
    ("sentiment", ("sentiment", "news", "social", "buzz", "mood", "tone")),
    ("price_volume", ("price", "volume", "return", "vwap", "turnover")),
]


class FieldRecord:
    __slots__ = (
        "id", "description", "dataset", "dataset_name", "category",
        "subcategory", "type", "regions", "delays", "universes",
        "coverage", "date_coverage", "alpha_count", "multiplier", "availability",
    )

    def __init__(self, fid, raw):
        self.id = fid
        self.description = str(raw.get("description") or "")
        ds = raw.get("dataset")
        if isinstance(ds, dict):
            self.dataset = str(ds.get("id") or "")
            self.dataset_name = str(ds.get("name") or "")
        else:
            self.dataset = str(ds or "")
            self.dataset_name = self.dataset
        cat = raw.get("category")
        if isinstance(cat, dict):
            self.category = str(cat.get("name") or cat.get("id") or "")
        else:
            self.category = str(cat or "")
        sub = raw.get("subcategory")
        if isinstance(sub, dict):
            self.subcategory = str(sub.get("name") or sub.get("id") or "")
        else:
            self.subcategory = str(sub or "")
        self.type = str(raw.get("type") or "").upper()
        self.regions = {str(r).upper() for r in _as_list(raw, "regions", "region")}
        self.delays = set()
        for d in _as_list(raw, "delays", "delay"):
            try:
                self.delays.add(int(str(d)))
            except (TypeError, ValueError):
                continue
        self.universes = {str(u) for u in _as_list(raw, "universes", "universe")}
        self.availability = [tuple(v) for v in raw.get("availability", [])
                             if isinstance(v,(list,tuple)) and len(v)==7]
        self.coverage = _as_float(raw.get("maxCoverage", raw.get("coverage")), 0.0)
        self.date_coverage = _as_float(raw.get("dateCoverage"), 0.0)
        self.alpha_count = int(_as_float(raw.get("maxAlphaCount", raw.get("alphaCount")), 0.0))
        self.multiplier = _as_float(raw.get("bestPyramidMultiplier", raw.get("pyramidMultiplier")), 1.0)
        if self.multiplier <= 0:
            self.multiplier = 1.0

    def available(self, region, delay, universe=None):
        if self.availability:
            return any(v[0]==region and int(v[1])==int(delay)
                       and (universe is None or v[2]==universe) for v in self.availability)
        # Legacy artifacts cannot establish joint support. They remain usable
        # for offline exploratory build stats, but strict preflight rejects them.
        return (region in self.regions and int(delay) in self.delays
                and (universe is None or universe in self.universes))

    def for_axis(self, region, delay, universe):
        matches=[v for v in self.availability if v[0]==region and int(v[1])==int(delay)
                 and v[2]==universe]
        if not matches:
            return self
        rec=copy.copy(self)
        rec.coverage=float(matches[-1][3]); rec.multiplier=float(matches[-1][4])
        rec.alpha_count=int(matches[-1][5]); rec.date_coverage=float(matches[-1][6])
        return rec

    @property
    def coverage_mode(self):
        return "direct" if self.coverage >= F2.BACKFILL_BELOW_COVERAGE else "backfill"


def _as_list(raw, plural_key, singular_key):
    v = raw.get(plural_key)
    if isinstance(v, (list, tuple, set)):
        return list(v)
    if v is not None:
        return [v]
    s = raw.get(singular_key)
    if s is None:
        return []
    return [s]


def _as_float(v, default):
    try:
        f = float(v)
        if math.isfinite(f):
            return f
        return default
    except (TypeError, ValueError):
        return default


def term_key(field_id):
    """Split a field id around its LAST numeric token so term-structure siblings
    (m1atmiv vs m2atmiv, fnd28_value_05a vs _06a) share a stem. Returns
    (stem_with_placeholder, index) or (None, None)."""
    matches = list(_NUM_RE.finditer(field_id or ""))
    if not matches:
        return None, None
    m = matches[-1]
    try:
        idx = int(m.group())
    except ValueError:
        return None, None
    stem = field_id[: m.start()] + "#N#" + field_id[m.end():]
    return stem, idx


def semantic_pair_key(field_id):
    """If field_id contains exactly one half of a known semantic pair, return
    (stem_with_placeholder, side). Side 0 = first token of the pair."""
    fid = (field_id or "").lower()
    tokens = {t for t in _TOKEN_SPLIT_RE.split(fid) if t}
    found = None
    for a, b in SEMANTIC_PAIRS:
        a_in, b_in = a in tokens, b in tokens
        if a_in == b_in:
            continue
        if found is not None:
            return None, None
        found = (a, b, 0 if a_in else 1)
    if not found:
        return None, None
    a, b, side = found
    present = a if side == 0 else b
    stem = re.sub(
        r"(?<![a-z0-9])" + re.escape(present) + r"(?![a-z0-9])", "#P#", fid, count=1
    )
    return stem, side


def family_of(field_id, description, category):
    """Template-family routing on id + description + category keywords."""
    blob = ((field_id or "").replace("_", " ") + " " + (description or "")
            + " " + (category or "")).lower()
    for fam, kws in _FAMILY_KEYWORDS:
        if any(k in blob for k in kws):
            return fam
    return "default"


class CatalogIndex:
    def __init__(self, path=None):
        path = Path(path or F2.CATALOG_PATH)
        self.path=path
        self.catalog_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open("r", encoding="utf-8") as fh:
            blob = json.load(fh)
        raw_fields = blob.get("fields") if isinstance(blob, dict) else None
        if raw_fields is None:
            # tolerate a bare list/dict of records
            raw_fields = blob
        self.note = blob.get("note", "") if isinstance(blob, dict) else ""
        self.fields = {}
        if isinstance(raw_fields, dict):
            items = raw_fields.items()
        else:
            items = ((r.get("id"), r) for r in raw_fields if isinstance(r, dict))
        for fid, raw in items:
            if not fid or not isinstance(raw, dict):
                continue
            self.fields[fid] = FieldRecord(fid, raw)
        # crowding normalization bounds (log space), computed once
        logs = [math.log1p(f.alpha_count) for f in self.fields.values()]
        self._crowd_lo = min(logs) if logs else 0.0
        self._crowd_hi = max(logs) if logs else 1.0
        if self._crowd_hi <= self._crowd_lo:
            self._crowd_hi = self._crowd_lo + 1.0

    # --- scoring ---------------------------------------------------------------
    def _norm_crowd(self, alpha_count):
        x = math.log1p(max(0, alpha_count))
        return max(0.0, min(1.0, (x - self._crowd_lo) / (self._crowd_hi - self._crowd_lo)))

    def priority_score(self, rec):
        """Consultant priority score (finding #2): pyramid-value led, crowding
        damped, sweet-spot maturity; multiplied by multiplier**gamma so the
        ranking itself optimizes expected platform value."""
        value = max(0.0, min(1.0, rec.multiplier - 1.0))
        proven = min(1.0, rec.alpha_count / F2.PROVEN_FULL_AT) if F2.PROVEN_FULL_AT > 0 else 1.0
        uncrowded = 1.0 - self._norm_crowd(rec.alpha_count)
        maturity = proven * uncrowded
        # Virgin high-multiplier fields deserve a shot even with alphaCount 0:
        # blend a floor so maturity never zeroes out a >=1.8x field.
        if rec.alpha_count == 0 and rec.multiplier >= 1.8:
            maturity = max(maturity, 0.5)
        coverage = max(0.0, min(1.0, rec.coverage))
        history = max(0.0, min(1.0, rec.date_coverage))
        simplicity = F2.SIMPLICITY_BY_TYPE.get(rec.type, 0.0)
        score = (F2.W_VALUE * value + F2.W_MATURITY * maturity
                 + F2.W_COVERAGE * coverage + F2.W_HISTORY * history
                 + F2.W_SIMPLICITY * simplicity)
        crowd_mult = max(F2.CROWD_FLOOR, 1.0 - F2.CROWD_PENALTY * self._norm_crowd(rec.alpha_count))
        score *= crowd_mult
        score *= rec.multiplier ** F2.PYRAMID_GAMMA
        return score

    # --- selections ------------------------------------------------------------
    def signal_pool(self, region, delay, universe=None):
        """Ranked candidate pool for one campaign: available MATRIX/VECTOR fields
        passing the coverage/crowding floors (finding #1 tier 1). Returns a list
        of (score, rec) sorted best-first, capped at CANDIDATE_POOL_MAX."""
        out = []
        for rec in self.fields.values():
            if rec.type not in ("MATRIX", "VECTOR"):
                continue
            if not rec.available(region, delay, universe):
                continue
            if universe is not None:
                rec = rec.for_axis(region, delay, universe)
            if rec.coverage < F2.POOL_MIN_COVERAGE:
                continue
            if rec.alpha_count > F2.POOL_MAX_ALPHA_COUNT:
                continue
            out.append((self.priority_score(rec), rec))
        out.sort(key=lambda t: t[0], reverse=True)
        return out[: F2.CANDIDATE_POOL_MAX]

    def group_keys(self, region, delay, limit=None, universe=None):
        """Top GROUP fields usable as custom neutralization keys (finding #6),
        ranked by coverage then un-crowding. Delay membership is not enforced
        for GROUP fields (grouping keys are static classifications)."""
        limit = limit or F2.GROUP_KEYS_MAX
        cands=[]
        for rec in self.fields.values():
            if rec.type != "GROUP" or not rec.available(region,delay,universe):
                continue
            rec=rec.for_axis(region,delay,universe) if universe else rec
            if rec.coverage>=F2.GROUP_KEYS_MIN_COVERAGE:
                cands.append(rec)
        cands.sort(key=lambda r: (r.coverage, -r.alpha_count), reverse=True)
        return cands[:limit]

    def term_pairs(self, records):
        """Adjacent term-structure pairs within one dataset among `records`.
        Returns list of (rec_near, rec_far) capped per family."""
        groups = defaultdict(list)
        for rec in records:
            # Numeric suffixes can be embedding components, not maturities.
            # Require explicit tenor/horizon evidence before creating spreads.
            blob=(rec.id+" "+rec.description).lower()
            if not re.search(r"month|week|day|year|tenor|maturit|expir|term.structure|horizon|\bm\d",blob):
                continue
            stem, idx = term_key(rec.id)
            if stem is None:
                continue
            groups[(rec.dataset, stem)].append((idx, rec))
        pairs = []
        for members in groups.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda t: t[0])
            added = 0
            for (_, a), (_, b) in zip(members, members[1:]):
                if added >= F2.TERM_SPREAD_MAX_PER_FAMILY:
                    break
                if a.type != b.type:
                    continue
                pairs.append((a, b))
                added += 1
        return pairs

    def semantic_pairs_in(self, records):
        """Complete semantic pairs (both sides present) within `records`."""
        sides = defaultdict(dict)
        for rec in records:
            stem, side = semantic_pair_key(rec.id)
            if stem is None:
                continue
            sides[(rec.dataset, stem)].setdefault(side, rec)
        out = []
        for d in sides.values():
            if 0 in d and 1 in d:
                out.append((d[0], d[1]))
        return out

    def observed_universes(self, region, delay):
        counts=defaultdict(int)
        for rec in self.fields.values():
            for uni in {v[2] for v in rec.availability
                        if v[0]==region and int(v[1])==int(delay)}:
                if rec.type in ("MATRIX","VECTOR"):
                    counts[uni]+=1
        return [u for u,_ in sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))]

    def validate_expression(self, expression, region, delay, universe):
        from forge2_expression import field_tokens, BUILTIN_GROUPS, type_errors
        errors=[]
        metadata={}
        for token in set(field_tokens(expression)):
            if token in BUILTIN_GROUPS:
                continue
            rec=self.fields.get(token)
            if rec is None:
                errors.append("UNKNOWN_FIELD:"+token)
                continue
            metadata[token]={"type":rec.type}
            if not rec.availability:
                errors.append("UNKNOWN_JOINT_AVAILABILITY:"+token)
            elif not rec.available(region,delay,universe):
                errors.append("UNOBSERVED_SETTINGS:"+token)
        errors.extend(type_errors(expression,metadata))
        return not errors, list(dict.fromkeys(errors))

    # --- reporting ---------------------------------------------------------------
    def campaign_stats(self, region, delay):
        pool = self.signal_pool(region, delay)
        frontier = [
            (s, r) for s, r in pool
            if r.multiplier >= F2.FRONTIER_MULTIPLIER
            and r.alpha_count <= F2.FRONTIER_MAX_ALPHAS and r.coverage >= 0.5
        ]
        datasets = defaultdict(int)
        for _, r in pool:
            datasets[r.dataset] += 1
        return {
            "region": region,
            "delay": delay,
            "pool": len(pool),
            "frontier": len(frontier),
            "datasets": len(datasets),
            "vectors": sum(1 for _, r in pool if r.type == "VECTOR"),
            "group_keys": len(self.group_keys(region, delay)),
        }
