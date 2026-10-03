```python
#!/usr/bin/env python3
"""analyze_run.py -- Brain Forge run introspection report.

A standalone, READ-ONLY analyzer for brain_memory.db. It answers the three
questions you actually care about after a run:

  1. WHAT did the engine generate?   -> full population + per-alpha stats
  2. HOW did it evolve?              -> generation-by-generation progression
                                        and seed-vs-evolved value-add
  3. WHAT is it doing structurally?  -> operator usage + shape diversity, so you
                                        can see whether the population explores
                                        rich shapes or collapses onto one template

Run it any time AFTER (or during a pause of) orchestrator.py:

    python analyze_run.py                  # console report + run_report.md
    python analyze_run.py --top 40         # list more top alphas
    python analyze_run.py --json out.json  # also dump machine-readable stats
    python analyze_run.py --db other.db    # point at a different database

It opens the database in read-only mode and never writes to it, so it is safe
to run alongside a live engine (it just sees a consistent snapshot).

NOTE ON LINEAGE: the engine records the GENERATION each alpha was scored in but
not per-alpha parentage (there is no parent_id column), so "evolution" here is
reconstructed from generation-level trends and the seed (gen 0) vs evolved
(gen > 0) comparison -- not a per-alpha family tree. A true lineage graph would
require adding a parent_id column to db_manager.save_alpha and having the
genetic engine record each child's parents.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime

DEFAULT_DB = os.getenv("BRAINFORGE_DB", "brain_memory.db")

# Bare tokens that look like fields but are settings keywords, so they must be
# excluded from the "distinct data fields" count used to classify shapes.
_NON_FIELD_TOKENS = {"SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE",
                     "TRUE", "FALSE"}

# Structural markers used when judging population diversity.
_TURNOVER_GATES = ("trade_when",)
_SPREAD_OPS = ("subtract", "add")

_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def connect_ro(db_path):
    """Open the database read-only so the analyzer can never corrupt a live run."""
    if not os.path.exists(db_path):
        return None
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt(value, spec=".3f", dash="-"):
    if value is None:
        return dash
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def _fit(row):
    return row["fitness"] if row["fitness"] is not None else float("-inf")


def _stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "min": None, "max": None, "mean": None}
    return {"n": len(vals), "min": min(vals), "max": max(vals),
            "mean": sum(vals) / len(vals)}


def operators_in(expression):
    """Function-call tokens (operators) used in an expression."""
    return _CALL_RE.findall(expression or "")


def fields_in(expression):
    """Heuristic: distinct DATA-FIELD leaf tokens -- lowercase identifiers NOT
    immediately followed by '(' (those are operator calls) and not settings
    keywords. Used to classify single- vs multi-field alphas."""
    if not expression:
        return set()
    calls = set(operators_in(expression))
    fields = set()
    for m in _IDENT_RE.finditer(expression):
        tok = m.group(0)
        if expression[m.end():].lstrip().startswith("("):
            continue  # operator call
        if tok in calls or tok in _NON_FIELD_TOKENS or tok.isupper():
            continue
        fields.add(tok)
    return fields


def classify_shape(expression):
    opset = set(operators_in(expression))
    flds = fields_in(expression)
    return {
        "n_fields": len(flds),
        "multi_field": len(flds) >= 2,
        "turnover_gated": any(g in opset for g in _TURNOVER_GATES),
        "has_spread": any(s in opset for s in _SPREAD_OPS),
        "neutralized": "group_neutralize" in opset,
        "vector_collapsed": "vec_avg" in opset or "vec_sum" in opset,
        "ts_backfilled": "ts_backfill" in opset,
    }


def render_table(headers, rows):
    """GitHub-style pipe table -- renders as a real table in run_report.md and
    stays readable in a terminal."""
    rows = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(c))

    def fmt_row(cells):
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    out = [fmt_row(headers),
           "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"]
    out += [fmt_row(row) for row in rows]
    return "\n".join(out)


def load_rows(conn):
    cols = ("expression", "universe", "decay", "alpha_id", "generation",
            "sharpe", "turnover", "fitness", "ast_depth", "skew", "kurtosis",
            "track_record_length", "max_correlation", "returns", "oos_sharpe",
            "is_qualified", "is_tuned", "timestamp")
    cur = conn.execute(f"SELECT {', '.join(cols)} FROM alpha_population")
    return [dict(r) for r in cur.fetchall()]


def build_report(rows, top=20, max_expr=90):
    scored = [r for r in rows if r["sharpe"] is not None]
    unscored = [r for r in rows if r["sharpe"] is None]
    lines = []
    data = {}

    # ---- 1. Summary --------------------------------------------------------
    gens = sorted({r["generation"] for r in scored if r["generation"] is not None})
    fitnesses = [r["fitness"] for r in scored if r["fitness"] is not None]
    sharpes = [r["sharpe"] for r in scored]
    qualified = [r for r in scored if r["is_qualified"]]
    tuned = [r for r in scored if r["is_tuned"]]
    times = [r["timestamp"] for r in rows if r["timestamp"]]
    summary = {
        "total_rows": len(rows),
        "scored": len(scored),
        "unscored_seeds": len(unscored),
        "qualified": len(qualified),
        "tuned": len(tuned),
        "generations": (min(gens), max(gens)) if gens else None,
        "best_fitness": max(fitnesses) if fitnesses else None,
        "best_sharpe": max(sharpes) if sharpes else None,
        "time_range": (min(times), max(times)) if times else None,
    }
    data["summary"] = summary

    lines.append("# Brain Forge -- Run Report")
    lines.append("")
    lines.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    lines.append(f"- Alphas recorded: **{len(rows)}**  (scored: **{len(scored)}**, unscored seeds: {len(unscored)})")
    if gens:
        lines.append(f"- Generations covered: **{min(gens)} -> {max(gens)}**")
    lines.append(f"- Qualified (passed gates): **{len(qualified)}**   |   Refined/tuned: **{len(tuned)}**")
    lines.append(f"- Best fitness: **{_fmt(summary['best_fitness'], '.4f')}**   |   Best Sharpe: **{_fmt(summary['best_sharpe'])}**")
    if summary["time_range"]:
        lines.append(f"- First record: {summary['time_range'][0]}   |   Last record: {summary['time_range'][1]}")
    lines.append("")

    # ---- 2. Evolution by generation ---------------------------------------
    lines.append("## Evolution by generation")
    lines.append("")
    lines.append("Rising best/mean fitness means the genetic engine is adding value; "
                 "a flat line after the first few generations means it has plateaued.")
    lines.append("")
    by_gen = {}
    for r in scored:
        by_gen.setdefault(r["generation"], []).append(r)
    gen_rows = []
    gen_data = []
    for g in sorted(by_gen, key=lambda x: (x is None, x)):
        grp = by_gen[g]
        f = _stats([x["fitness"] for x in grp])
        s = _stats([x["sharpe"] for x in grp])
        t = _stats([x["turnover"] for x in grp])
        d = _stats([x["ast_depth"] for x in grp])
        q = sum(1 for x in grp if x["is_qualified"])
        label = "0 (seed)" if g == 0 else (g if g is not None else "?")
        gen_rows.append([label, len(grp), _fmt(f["max"], ".4f"), _fmt(f["mean"], ".4f"),
                         _fmt(s["max"]), _fmt(s["mean"]), _fmt(t["mean"]),
                         _fmt(d["mean"], ".1f"), q])
        gen_data.append({"generation": g, "n": len(grp), "fitness": f,
                         "sharpe": s, "turnover": t, "ast_depth": d, "qualified": q})
    lines.append(render_table(
        ["Gen", "N", "Best fit", "Mean fit", "Best Shp", "Mean Shp",
         "Mean turn", "Mean depth", "Qual"], gen_rows))
    lines.append("")
    data["by_generation"] = gen_data

    # ---- 3. Seed vs evolved value-add -------------------------------------
    seed_grp = by_gen.get(0, [])
    evolved = [r for g, grp in by_gen.items() if g not in (None, 0) for r in grp]
    sv = _stats([x["fitness"] for x in seed_grp])
    ev = _stats([x["fitness"] for x in evolved])
    lines.append("## Seed vs evolved value-add")
    lines.append("")
    lines.append(render_table(
        ["Cohort", "N", "Best fit", "Mean fit"],
        [["Seeds (gen 0)", sv["n"], _fmt(sv["max"], ".4f"), _fmt(sv["mean"], ".4f")],
         ["Evolved (gen>0)", ev["n"], _fmt(ev["max"], ".4f"), _fmt(ev["mean"], ".4f")]]))
    if sv["max"] is not None and ev["max"] is not None:
        delta = ev["max"] - sv["max"]
        verdict = ("the GA IMPROVED on the best seed" if delta > 0
                   else "the GA did NOT beat the best seed -- check mutation/crossover")
        lines.append("")
        lines.append(f"Best-fitness delta (evolved - seed): **{_fmt(delta, '+.4f')}** -> {verdict}.")
    lines.append("")
    data["seed_vs_evolved"] = {"seeds": sv, "evolved": ev}

    # ---- 4. Structural diversity ------------------------------------------
    shapes = [classify_shape(r["expression"]) for r in scored]
    n = len(shapes) or 1

    def pct(key):
        return 100.0 * sum(1 for s in shapes if s[key]) / n

    field_hist = Counter(s["n_fields"] for s in shapes)
    lines.append("## Structural diversity (scored population)")
    lines.append("")
    lines.append("Heuristic shape analysis of the expressions actually scored. If "
                 "'multi-field' and 'turnover-gated' are near 0%, the population has "
                 "collapsed onto single-field shapes and the rich templates are not "
                 "surviving -- the lever is seed budget + mutation/crossover.")
    lines.append("")
    lines.append(render_table(
        ["Shape marker", "% of scored"],
        [["Multi-field (>=2 fields)", _fmt(pct("multi_field"), ".1f")],
         ["Turnover-gated (trade_when)", _fmt(pct("turnover_gated"), ".1f")],
         ["Term-structure spread (subtract/add)", _fmt(pct("has_spread"), ".1f")],
         ["Group-neutralized", _fmt(pct("neutralized"), ".1f")],
         ["VECTOR-collapsed (vec_avg/sum)", _fmt(pct("vector_collapsed"), ".1f")],
         ["ts_backfilled", _fmt(pct("ts_backfilled"), ".1f")]]))
    lines.append("")
    lines.append("Field-count distribution: " +
                 ", ".join(f"{k} field(s): {v}" for k, v in sorted(field_hist.items())))
    lines.append("")
    data["structural"] = {
        "multi_field_pct": pct("multi_field"),
        "turnover_gated_pct": pct("turnover_gated"),
        "spread_pct": pct("has_spread"),
        "neutralized_pct": pct("neutralized"),
        "vector_collapsed_pct": pct("vector_collapsed"),
        "field_count_hist": dict(field_hist),
    }

    # ---- 5. Operator usage ------------------------------------------------
    op_counter = Counter()
    op_alpha_counter = Counter()
    for r in scored:
        ops = operators_in(r["expression"])
        op_counter.update(ops)
        op_alpha_counter.update(set(ops))
    lines.append("## Operator usage")
    lines.append("")
    op_rows = [[op, cnt, op_alpha_counter[op], _fmt(100.0 * op_alpha_counter[op] / n, ".1f")]
               for op, cnt in op_counter.most_common(20)]
    lines.append(render_table(["Operator", "Total uses", "# alphas", "% alphas"], op_rows))
    lines.append("")
    data["operator_usage"] = {op: {"total": c, "alphas": op_alpha_counter[op]}
                              for op, c in op_counter.items()}

    # ---- 6. Distribution by universe / decay ------------------------------
    uni = Counter(r["universe"] for r in scored)
    dec = Counter(r["decay"] for r in scored)
    lines.append("## Distribution")
    lines.append("")
    lines.append("By universe: " + ", ".join(f"{k}: {v}" for k, v in uni.most_common()))
    lines.append("")
    lines.append("By decay: " + ", ".join(
        f"{k}: {v}" for k, v in sorted(dec.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    lines.append("")
    data["distribution"] = {"universe": dict(uni),
                            "decay": {str(k): v for k, v in dec.items()}}

    # ---- 7. Top alphas by fitness -----------------------------------------
    ranked = sorted(scored, key=_fit, reverse=True)
    top_rows = []
    for i, r in enumerate(ranked[:top], 1):
        expr = r["expression"] or ""
        disp = (expr[:max_expr] + "...") if len(expr) > max_expr else expr
        glabel = "0" if r["generation"] == 0 else (r["generation"] if r["generation"] is not None else "?")
        top_rows.append([i, glabel, _fmt(r["fitness"], ".4f"), _fmt(r["sharpe"]),
                         _fmt(r["turnover"]), _fmt(r["returns"], ".4f"),
                         _fmt(r["oos_sharpe"]),
                         r["ast_depth"] if r["ast_depth"] is not None else "-",
                         "Y" if r["is_qualified"] else "-",
                         "Y" if r["is_tuned"] else "-", disp])
    lines.append(f"## Top {min(top, len(ranked))} alphas by fitness")
    lines.append("")
    lines.append(render_table(
        ["#", "Gen", "Fitness", "Sharpe", "Turn", "Returns", "OOS Shp",
         "Depth", "Qual", "Tuned", "Expression"], top_rows))
    lines.append("")
    data["top_alphas"] = ranked[:top]

    # ---- 8. Qualified / submittable candidates ----------------------------
    subs = [r for r in scored if r["is_qualified"] and r["alpha_id"]
            and r["alpha_id"] not in ("", "MANUAL_SEED")]
    subs.sort(key=_fit, reverse=True)
    lines.append("## Qualified / submittable candidates")
    lines.append("")
    if subs:
        sub_rows = []
        for r in subs:
            expr = r["expression"] or ""
            disp = (expr[:max_expr] + "...") if len(expr) > max_expr else expr
            sub_rows.append([r["alpha_id"], _fmt(r["fitness"], ".4f"), _fmt(r["sharpe"]),
                             _fmt(r["turnover"]), _fmt(r["max_correlation"]), disp])
        lines.append(render_table(
            ["Alpha ID", "Fitness", "Sharpe", "Turn", "MaxCorr", "Expression"], sub_rows))
    else:
        lines.append("_No qualified, server-registered candidates yet._")
    lines.append("")
    data["submittable"] = subs

    return "\n".join(lines), data


def main(argv=None):
    p = argparse.ArgumentParser(description="Brain Forge run introspection report.")
    p.add_argument("--db", default=DEFAULT_DB, help="path to brain_memory.db")
    p.add_argument("--top", type=int, default=20, help="how many top alphas to list")
    p.add_argument("--md", default="run_report.md", help="markdown output path ('' to skip)")
    p.add_argument("--json", default="", help="optional JSON stats output path")
    p.add_argument("--max-expr", type=int, default=90, help="expression truncation width")
    args = p.parse_args(argv)

    conn = connect_ro(args.db)
    if conn is None:
        print(f"Database not found: {args.db}\nRun orchestrator.py first (or pass --db).")
        return 1
    try:
        rows = load_rows(conn)
    except sqlite3.OperationalError as e:
        print(f"Could not read alpha_population from {args.db}: {e}")
        return 1
    finally:
        conn.close()

    if not rows:
        print("No alphas recorded yet. Run orchestrator.py first.")
        return 0

    text, data = build_report(rows, top=args.top, max_expr=args.max_expr)
    print(text)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"\nMarkdown report written to {args.md}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        print(f"JSON stats written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```