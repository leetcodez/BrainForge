Part of **Forge v2 — Consultant Overhaul (Sept 2026)**. Emits the rotating active vocabulary in the EXACT formats the stock engine consumes: `data_fields.json` (incl. compound expressions as MATRIX/direct rows — vector projections, disagreement ratios, term/semantic spreads), `seed_pool.json` (family templates + GROUP-key neutralization variants), and `forge2_field_meta.json` (pyramid/bandit sidecar). No engine file is modified; the vocabulary is swapped underneath it.
```python
"""Forge2 vocabulary builder: the two-tier vocabulary (finding #1) emitter.

Tier 1 (candidate pool): every available field for the campaign axes, ranked by
the consultant priority score -- built by forge2_catalog.
Tier 2 (active set): a rotating ~600-row working vocabulary chosen by the
dataset bandit, emitted in the EXACT formats the stock engine already consumes:

  * data_fields.json  -> config._load_harvested_vocabulary -> DATA_DICTIONARY /
    FIELD_GROUPS (breadth-first seeding + genetic mutation pool). Compound
    expressions (vector projections, disagreement ratios, term spreads) are
    emitted as type=MATRIX / coverageMode=direct rows so the stock loader
    passes them through verbatim; the GeneticEngine already registers inner
    field names of compound entries, so mutation reaches inside them.
  * seed_pool.json    -> llm_seed_generator (data-first seeding), including
    GROUP-key neutralization templates (finding #6) and the vector projection
    family (finding #5).
  * forge2_field_meta.json -> pyramid boost (forge2_factory) + bandit mapping
    (forge2_campaign): field/expr -> dataset, multiplier, family, class.

No engine file is modified; the vocabulary is swapped underneath it.
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

import forge2_config as F2
from forge2_catalog import family_of

_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
BACKFILL_WINDOW = 252


def load_live_operators(path=None, dir_fallback=None):
    """Live operator names. Accepts three sources: the repo operators.json
    (a bare list of operator dicts), a raw snapshot endpoint capture (a dict
    with slices -> rows, as produced by platform_snapshot.py), or a directory
    of per-operator json files. Returns a lowercase set."""
    names = set()
    path = Path(path or F2.OPERATORS_PATH)
    if path.exists() and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        rows = []
        if isinstance(data, list):
            rows = list(data)
        elif isinstance(data, dict):
            if isinstance(data.get("results"), list):
                rows = list(data["results"])
            for sl in data.get("slices") or []:
                if isinstance(sl, dict) and isinstance(sl.get("rows"), list):
                    rows.extend(sl["rows"])
        for op in rows:
            if isinstance(op, dict) and op.get("name"):
                names.add(str(op["name"]).lower())
    if not names:
        d = Path(dir_fallback or F2.OPERATORS_DIR_FALLBACK or "")
        if d and d.is_dir():
            for f in d.glob("*.json"):
                names.add(f.stem.lower())
    return names


def ops_in(expression):
    """Operator-call tokens in an expression/template (tokens followed by '(')."""
    return {m.group(1).lower() for m in _CALL_RE.finditer(expression or "")}


class VocabularyBuilder:
    def __init__(self, catalog, region, delay, live_ops, bandit=None, rng=None):
        self.catalog = catalog
        self.region = region
        self.delay = delay
        self.live_ops = {o.lower() for o in (live_ops or set())}
        self.bandit = bandit
        import random as _random
        self.rng = rng or _random.Random(F2.RANDOM_SEED)

    # --- template/expression helpers -------------------------------------------
    def _template_ok(self, text):
        if not self.live_ops:
            return True  # no metadata available -> do not over-filter
        return ops_in(text) <= self.live_ops

    @staticmethod
    def _operand(rec):
        """Type-correct scalar operand for a field (harvester parity): VECTOR ->
        vec_avg(id); sparse -> ts_backfill(..., 252)."""
        expr = rec.id
        if rec.type == "VECTOR":
            expr = "vec_avg(" + expr + ")"
        if rec.coverage_mode == "backfill":
            expr = "ts_backfill(" + expr + ", " + str(BACKFILL_WINDOW) + ")"
        return expr

    def _projection_expr(self, rec, projection):
        expr = projection + "(" + rec.id + ")"
        if rec.coverage_mode == "backfill":
            expr = "ts_backfill(" + expr + ", " + str(BACKFILL_WINDOW) + ")"
        return expr

    def _disagreement_expr(self, rec):
        """Coefficient of variation: vec_stddev / vec_avg with a guarded
        denominator -- the analyst-disagreement signal family."""
        core = ("divide(vec_stddev(" + rec.id + "), max(abs(vec_avg("
                + rec.id + ")), 0.0001))")
        if rec.coverage_mode == "backfill":
            core = "ts_backfill(" + core + ", " + str(BACKFILL_WINDOW) + ")"
        return core

    # --- selection ----------------------------------------------------------------
    def _choose_datasets(self, pool):
        """Rank datasets by mean field score; let the bandit pick the arms."""
        agg = defaultdict(lambda: {"n": 0, "score": 0.0, "mult": 0.0, "alphas": 0.0})
        for score, rec in pool:
            a = agg[rec.dataset]
            a["n"] += 1
            a["score"] += score
            a["mult"] += rec.multiplier
            a["alphas"] += rec.alpha_count
        ranked = sorted(
            agg.items(), key=lambda kv: kv[1]["score"] / kv[1]["n"], reverse=True
        )
        dataset_ids = [ds for ds, _ in ranked if ds]
        if self.bandit is not None:
            for ds, a in agg.items():
                if not ds:
                    continue
                self.bandit.ensure_arm(
                    ds, avg_multiplier=a["mult"] / a["n"],
                    avg_alpha_count=a["alphas"] / a["n"],
                )
            return self.bandit.sample_arms(dataset_ids, F2.ACTIVE_DATASET_ARMS)
        return dataset_ids[: F2.ACTIVE_DATASET_ARMS]

    # --- build ---------------------------------------------------------------------
    def build(self):
        pool = self.catalog.signal_pool(self.region, self.delay)
        by_dataset = defaultdict(list)
        for score, rec in pool:
            by_dataset[rec.dataset].append((score, rec))
        chosen = self._choose_datasets(pool)

        compound_budget = (
            F2.VECTOR_FIELDS_EXPANDED * F2.VECTOR_EXTRA_PER_FIELD
            + F2.VECTOR_DISAGREEMENT_MAX + F2.TERM_SPREAD_MAX_TOTAL
            + F2.SEMANTIC_SPREAD_MAX_TOTAL
        )
        base_budget = max(100, F2.ACTIVE_SET_MAX - compound_budget)

        active = []  # (score, rec)
        for ds in chosen:
            members = by_dataset.get(ds) or []
            take = members[: max(F2.ACTIVE_MIN_PER_ARM, F2.ACTIVE_PER_DATASET)]
            active.extend(take[: F2.ACTIVE_PER_DATASET])
        active.sort(key=lambda t: t[0], reverse=True)
        active = active[:base_budget]
        active_records = [rec for _, rec in active]
        score_of = {rec.id: s for s, rec in active}

        rows = []
        meta_fields = {}
        field_to_dataset = {}
        seen_ids = set()

        def add_row(expr_id, rec, ftype, mode, template_class, score, base_ids):
            if expr_id in seen_ids:
                return False
            seen_ids.add(expr_id)
            rows.append({
                "id": expr_id,
                "description": (rec.description if template_class == "base"
                                 else "forge2 " + template_class + ": " + ", ".join(base_ids)),
                "type": ftype,
                "dataset": rec.dataset,
                "category": rec.category,
                "subcategory": rec.subcategory,
                "coverage": round(rec.coverage, 4),
                "coverageMode": mode,
                "dateCoverage": round(rec.date_coverage, 4),
                "alphaCount": rec.alpha_count,
                "userCount": 0,
                "priorityScore": round(score, 4),
            })
            meta_fields[expr_id] = {
                "dataset": rec.dataset,
                "multiplier": rec.multiplier,
                "family": family_of(rec.id, rec.description, rec.category),
                "class": template_class,
                "base": list(base_ids),
            }
            return True

        # 1) base fields (raw ids; stock loader handles vec_avg/backfill wraps)
        for score, rec in active:
            add_row(rec.id, rec, rec.type, rec.coverage_mode, "base", score, [rec.id])
            field_to_dataset[rec.id] = rec.dataset

        # 2) extra vector projections (finding #5)
        vectors = [rec for rec in active_records if rec.type == "VECTOR"]
        vectors.sort(key=lambda r: score_of.get(r.id, 0.0), reverse=True)
        projections = [p for p in F2.VECTOR_EXTRA_PROJECTIONS if p in self.live_ops or not self.live_ops]
        for rec in vectors[: F2.VECTOR_FIELDS_EXPANDED]:
            for proj in projections[: F2.VECTOR_EXTRA_PER_FIELD]:
                expr = self._projection_expr(rec, proj)
                if not self._template_ok(expr):
                    continue
                add_row(expr, rec, "MATRIX", "direct", "vector_projection",
                        score_of.get(rec.id, 0.0) * 0.9, [rec.id])

        # 3) disagreement ratios (finding #5) -- analyst/sentiment vectors first
        if F2.VECTOR_DISAGREEMENT:
            added = 0
            for rec in vectors:
                if added >= F2.VECTOR_DISAGREEMENT_MAX:
                    break
                expr = self._disagreement_expr(rec)
                if not self._template_ok(expr):
                    break  # ops missing on this tenant -> skip the whole family
                if add_row(expr, rec, "MATRIX", "direct", "vector_disagreement",
                           score_of.get(rec.id, 0.0) * 0.85, [rec.id]):
                    added += 1

        # 4) term-structure spreads (finding #11)
        added_spreads = 0
        for near, far in self.catalog.term_pairs(active_records):
            if added_spreads >= F2.TERM_SPREAD_MAX_TOTAL:
                break
            expr = "subtract(" + self._operand(near) + ", " + self._operand(far) + ")"
            if not self._template_ok(expr):
                continue
            host = near if near.multiplier >= far.multiplier else far
            if add_row(expr, host, "MATRIX", "direct", "term_spread",
                       score_of.get(host.id, 0.0) * 0.9, [near.id, far.id]):
                added_spreads += 1

        # 5) semantic-pair spreads (finding #11)
        added_sem = 0
        for a, b in self.catalog.semantic_pairs_in(active_records):
            if added_sem >= F2.SEMANTIC_SPREAD_MAX_TOTAL:
                break
            expr = "subtract(" + self._operand(a) + ", " + self._operand(b) + ")"
            if not self._template_ok(expr):
                continue
            if add_row(expr, a, "MATRIX", "direct", "semantic_spread",
                       score_of.get(a.id, 0.0) * 0.9, [a.id, b.id]):
                added_sem += 1

        rows.sort(key=lambda r: r["priorityScore"], reverse=True)
        rows = rows[: F2.ACTIVE_SET_MAX]
        kept_ids = {r["id"] for r in rows}
        meta_fields = {k: v for k, v in meta_fields.items() if k in kept_ids}

        # 6) GROUP neutralization keys (finding #6)
        group_keys = [g.id for g in self.catalog.group_keys(self.region, self.delay)]

        seed_pool = self._build_seed_pool(rows, meta_fields, group_keys)

        meta = {
            "axes": {"region": self.region, "delay": self.delay},
            "generated_at": int(time.time()),
            "fields": meta_fields,
            "field_to_dataset": field_to_dataset,
            "group_keys": group_keys,
            "datasets_chosen": chosen,
        }
        stats = {
            "pool": len(pool),
            "datasets_chosen": len(chosen),
            "rows": len(rows),
            "classes": _count_classes(meta_fields),
            "group_keys": len(group_keys),
            "seed_pool": len(seed_pool),
            "templates": sum(len(r.get("templates") or []) for r in seed_pool),
        }
        return {"rows": rows, "seed_pool": seed_pool, "meta": meta, "stats": stats}

    # --- seed pool -------------------------------------------------------------------
    def _family_templates(self, operand, family):
        """Family-tailored templates (harvester parity + forge2 extensions).
        Placeholders {NEUTRALIZATION}/{LOOKBACK_SHORT}/{LOOKBACK_LONG} are filled
        by the stock seed generator."""
        if family == "options_vol":
            base = [
                "group_neutralize(rank(" + operand + "), {NEUTRALIZATION})",
                "group_neutralize(rank(ts_zscore(" + operand + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
                "group_neutralize(-rank(ts_av_diff(" + operand + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            ]
        elif family in ("analyst", "earnings_event"):
            base = [
                "group_neutralize(rank(" + operand + "), {NEUTRALIZATION})",
                "group_neutralize(rank(ts_delta(" + operand + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
                "group_neutralize(rank(ts_zscore(" + operand + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            ]
        elif family == "sentiment":
            base = [
                "group_neutralize(rank(ts_zscore(" + operand + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
                "group_neutralize(rank(ts_delta(" + operand + ", {LOOKBACK_SHORT})), {NEUTRALIZATION})",
            ]
        else:
            base = [
                "group_neutralize(rank(" + operand + "), {NEUTRALIZATION})",
                "group_neutralize(-rank(" + operand + "), {NEUTRALIZATION})",
                "group_neutralize(ts_zscore(" + operand + ", {LOOKBACK_LONG}), {NEUTRALIZATION})",
                "group_neutralize(sign(ts_delta(" + operand + ", {LOOKBACK_LONG})), {NEUTRALIZATION})",
            ]
        return [t for t in base if self._template_ok(t)]

    def _group_key_templates(self, operand, group_key):
        """Custom-key neutralization templates (finding #6): neutralize / rank
        WITHIN a catalog grouping field instead of the 4 builtin groups."""
        cands = [
            "group_neutralize(rank(" + operand + "), " + group_key + ")",
            "group_rank(" + operand + ", " + group_key + ")",
            "group_zscore(ts_delta(" + operand + ", {LOOKBACK_SHORT}), " + group_key + ")",
        ]
        return [t for t in cands if self._template_ok(t)]

    def _build_seed_pool(self, rows, meta_fields, group_keys):
        seed_pool = []
        gk_cycle = list(group_keys)
        gk_i = 0
        for row in rows:
            m = meta_fields.get(row["id"]) or {}
            cls = m.get("class", "base")
            fam = m.get("family", "default")
            if cls == "base":
                # rebuild the operand with type-correct wraps
                operand = row["id"]
                if row["type"] == "VECTOR":
                    operand = "vec_avg(" + operand + ")"
                if row["coverageMode"] == "backfill":
                    operand = "ts_backfill(" + operand + ", " + str(BACKFILL_WINDOW) + ")"
            else:
                operand = row["id"]  # compounds are already scalar expressions
            templates = self._family_templates(operand, fam)
            # GROUP-key variants on a rotating subset (finding #6)
            if gk_cycle and self.rng.random() < F2.GROUP_KEY_TEMPLATE_FRACTION:
                gk = gk_cycle[gk_i % len(gk_cycle)]
                gk_i += 1
                templates = templates[:2] + self._group_key_templates(operand, gk)[:2]
            templates = templates[: F2.SEED_TEMPLATE_MAX_PER_FIELD]
            if not templates:
                continue
            entry = dict(row)
            entry["templates"] = templates
            entry["seedReason"] = "forge2:" + cls
            seed_pool.append(entry)
        return seed_pool

    # --- write ---------------------------------------------------------------------
    def write(self, outdir):
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        built = self.build()
        (outdir / "data_fields.json").write_text(
            json.dumps(built["rows"], indent=1), encoding="utf-8")
        (outdir / "seed_pool.json").write_text(
            json.dumps(built["seed_pool"], indent=1), encoding="utf-8")
        (outdir / "forge2_field_meta.json").write_text(
            json.dumps(built["meta"], indent=1), encoding="utf-8")
        return built


def _count_classes(meta_fields):
    counts = defaultdict(int)
    for m in meta_fields.values():
        counts[m.get("class", "base")] += 1
    return dict(counts)
```