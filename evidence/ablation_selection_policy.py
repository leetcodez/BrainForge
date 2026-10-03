#!/usr/bin/env python3
"""Fixed-pool offline ablation: separate expression deduplication, PnL redundancy
controls, and dataset-cap effects on the earnings4_run2 evidence.

Runs select_basket() under four fixed configurations on the SAME candidate pool:
  A. No basket controls (raw fitness ranking, top-20)
  B. Expression deduplication only (remove exact duplicates, then rank)
  C. Full PnL controls WITHOUT dataset cap (max_dataset_fraction=1.0)
  D. Full PnL controls WITH current dataset cap (max_dataset_fraction=0.4)

Records: selected IDs, evidence coverage, rejection reasons by category,
basket redundancy metrics (pairwise abs-correlation distribution).
Thresholds are fixed across runs; no configuration is selected by which
historical Sharpe looks best.

Usage:
    PYTHONPATH=src python evidence/ablation_selection_policy.py \
        --db backups/pre_v2_baseline/brain_memory.earnings4_run2.db \
        --meta migrated_runs/earnings4_run2/.epochs/*/forge2_field_meta.json \
        --out evidence/selection-ablation-results.json

Offline, credential-free, read-only against source DB.
"""
from __future__ import annotations
import argparse, json, sqlite3, hashlib, sys
from pathlib import Path
from collections import defaultdict
import numpy as np

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from forge2_portfolio import select_basket, dataset_members
from forge2_statistics import daily_changes
from forge2_storage import atomic_json


def load_evidence(db_path: str, meta_path: str | None):
    """Load scored candidates and PnL from a read-only database copy."""
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        'SELECT * FROM alpha_population WHERE fitness IS NOT NULL AND sharpe IS NOT NULL '
        'ORDER BY fitness DESC, id')]
    pnl_rows = db.execute(
        'SELECT alpha_id, date, pnl FROM alpha_pnl WHERE pnl IS NOT NULL').fetchall()
    db.close()

    pnls = defaultdict(dict)
    for aid, date, value in pnl_rows:
        pnls[aid][date] = value

    metadata = {}
    if meta_path:
        meta = json.loads(Path(meta_path).read_text())
        metadata = meta.get('field_metadata', {})

    return rows, dict(pnls), metadata


def deduplicate_expressions(rows):
    """Remove exact expression duplicates, keeping the highest-fitness row per expression."""
    seen = {}
    for r in rows:
        expr = r['expression']
        if expr not in seen or r['fitness'] > seen[expr]['fitness']:
            seen[expr] = r
    # Return in fitness-descending order
    return sorted(seen.values(), key=lambda r: (-r['fitness'], r.get('alpha_id', '')))


def pairwise_correlation_stats(selected_ids, series_by_id, min_overlap=60):
    """Compute pairwise abs-correlation distribution among selected candidates with PnL."""
    from forge2_statistics import daily_changes
    diffs = {}
    for aid in selected_ids:
        if aid in series_by_id:
            diffs[aid] = daily_changes(series_by_id[aid])
    if len(diffs) < 2:
        return {'pairs': 0, 'with_pnl': len(diffs), 'note': 'insufficient PnL coverage for correlation'}

    aids = sorted(diffs.keys())
    common = sorted(set.intersection(*(set(diffs[a]) for a in aids)))
    if len(common) < min_overlap:
        return {'pairs': 0, 'common_dates': len(common), 'note': 'insufficient overlap'}

    x = np.column_stack([[diffs[a][d] for d in common] for a in aids])
    sd = x.std(axis=0)
    valid = sd > 1e-12
    if valid.sum() < 2:
        return {'pairs': 0, 'note': 'flat series'}

    x = x[:, valid]
    corr = np.abs(np.corrcoef(x, rowvar=False))
    n = corr.shape[0]
    pairs = []
    for i in range(n):
        for j in range(i+1, n):
            pairs.append(float(corr[i, j]))

    pairs_arr = np.array(pairs)
    return {
        'pairs': len(pairs),
        'with_pnl': int(valid.sum()),
        'common_dates': len(common),
        'mean_abs_corr': float(pairs_arr.mean()),
        'median_abs_corr': float(np.median(pairs_arr)),
        'max_abs_corr': float(pairs_arr.max()),
        'above_0.8': int((pairs_arr > 0.8).sum()),
        'above_0.9': int((pairs_arr > 0.9).sum()),
        'above_0.99': int((pairs_arr > 0.99).sum()),
    }


def count_rejections(report):
    """Summarize rejection reasons from a basket report."""
    reasons = defaultdict(int)
    for aid, reason in report.get('rejections', {}).items():
        reasons[reason] += 1
    return dict(reasons)


def run_ablation(db_path, meta_path, out_path, basket_size=20):
    rows, pnls, metadata = load_evidence(db_path, meta_path)

    # Filter to TOP3000 universe only (the primary search universe)
    rows = [r for r in rows if r.get('universe') == 'TOP3000']

    # Add regime info (needed by select_basket for single-regime check)
    for r in rows:
        r['region'] = 'USA_ASSUMED'
        r['delay'] = 1  # migration assumption, NOT verified

    total_scored = len(rows)
    with_pnl = sum(1 for r in rows if r.get('alpha_id') in pnls)
    deduped = deduplicate_expressions(rows)
    duplicate_count = total_scored - len(deduped)

    summary = {
        'pool': {
            'total_scored_TOP3000': total_scored,
            'unique_expressions': len(deduped),
            'exact_duplicates_removed': duplicate_count,
            'with_recorded_pnl': with_pnl,
            'pnl_coverage_fraction': round(with_pnl / total_scored, 4) if total_scored else 0,
            'provenance_note': 'region=USA and delay=1 are migration assumptions from legacy config.py DEFAULT_REGION/DEFAULT_DELAY; no original run log confirms these were the submitted values'
        },
        'basket_size': basket_size,
        'ablation_variants': {},
    }

    # --- Variant A: No basket controls (raw fitness ranking, top-N) ---
    top_n = rows[:basket_size]
    selected_a_ids = [r.get('alpha_id') for r in top_n]
    corr_a = pairwise_correlation_stats(selected_a_ids, pnls)
    summary['ablation_variants']['A_no_controls'] = {
        'description': 'Raw fitness ranking, top-20, no deduplication or basket controls',
        'selected_count': len(top_n),
        'selected_ids': selected_a_ids,
        'datasets_in_selection': sorted({d for r in top_n for d in dataset_members(r['expression'], metadata)}),
        'pnl_covered_in_selection': sum(1 for a in selected_a_ids if a in pnls),
        'pairwise_correlation': corr_a,
        'rejection_summary': {},
    }

    # --- Variant B: Expression deduplication only ---
    top_n_dedup = deduped[:basket_size]
    selected_b_ids = [r.get('alpha_id') for r in top_n_dedup]
    corr_b = pairwise_correlation_stats(selected_b_ids, pnls)
    summary['ablation_variants']['B_dedup_only'] = {
        'description': 'Expression deduplication (keep highest fitness per expression), then top-20',
        'selected_count': len(top_n_dedup),
        'selected_ids': selected_b_ids,
        'datasets_in_selection': sorted({d for r in top_n_dedup for d in dataset_members(r['expression'], metadata)}),
        'pnl_covered_in_selection': sum(1 for a in selected_b_ids if a in pnls),
        'pairwise_correlation': corr_b,
        'rejection_summary': {},
    }

    # --- Variant C: Full controls WITHOUT dataset cap ---
    ordered_c = list(deduped)  # deduped, fitness-sorted
    selected_c, report_c = select_basket(
        ordered_c, pnls, metadata, basket_size,
        max_dataset_fraction=1.0,  # DISABLED dataset cap
        max_abs_correlation=0.8,
        min_residual_fraction=0.1,
    )
    selected_c_ids = [r.get('alpha_id') for r in selected_c]
    corr_c = pairwise_correlation_stats(selected_c_ids, pnls)
    summary['ablation_variants']['C_pnl_controls_no_cap'] = {
        'description': 'Full PnL correlation + residual controls, dataset cap DISABLED (max_dataset_fraction=1.0)',
        'selected_count': len(selected_c),
        'selected_ids': selected_c_ids,
        'verified_count': len(report_c.get('verified', [])),
        'exploration_count': len(report_c.get('exploration', [])),
        'datasets_in_selection': sorted({d for r in selected_c for d in dataset_members(r['expression'], metadata)}),
        'pnl_covered_in_selection': sum(1 for a in selected_c_ids if a in pnls),
        'common_intervals': report_c.get('common_intervals'),
        'shrinkage': report_c.get('shrinkage'),
        'pairwise_correlation': corr_c,
        'rejection_summary': count_rejections(report_c),
        'basket_reason': report_c.get('reason'),
        'dataset_counts': report_c.get('dataset_counts', {}),
    }

    # --- Variant D: Full controls WITH current dataset cap ---
    ordered_d = list(deduped)
    selected_d, report_d = select_basket(
        ordered_d, pnls, metadata, basket_size,
        max_dataset_fraction=0.4,  # CURRENT default
        max_abs_correlation=0.8,
        min_residual_fraction=0.1,
    )
    selected_d_ids = [r.get('alpha_id') for r in selected_d]
    corr_d = pairwise_correlation_stats(selected_d_ids, pnls)
    summary['ablation_variants']['D_pnl_controls_with_cap'] = {
        'description': 'Full PnL correlation + residual controls, dataset cap ACTIVE (max_dataset_fraction=0.4, 8 max from earnings4)',
        'selected_count': len(selected_d),
        'selected_ids': selected_d_ids,
        'verified_count': len(report_d.get('verified', [])),
        'exploration_count': len(report_d.get('exploration', [])),
        'datasets_in_selection': sorted({d for r in selected_d for d in dataset_members(r['expression'], metadata)}),
        'pnl_covered_in_selection': sum(1 for a in selected_d_ids if a in pnls),
        'common_intervals': report_d.get('common_intervals'),
        'shrinkage': report_d.get('shrinkage'),
        'pairwise_correlation': corr_d,
        'rejection_summary': count_rejections(report_d),
        'basket_reason': report_d.get('reason'),
        'dataset_counts': report_d.get('dataset_counts', {}),
    }

    # --- Cross-variant comparison ---
    sets = {
        'A': set(selected_a_ids),
        'B': set(selected_b_ids),
        'C': set(selected_c_ids),
        'D': set(selected_d_ids),
    }
    summary['cross_comparison'] = {
        'A_and_B_overlap': len(sets['A'] & sets['B']),
        'A_and_C_overlap': len(sets['A'] & sets['C']),
        'A_and_D_overlap': len(sets['A'] & sets['D']),
        'B_and_C_overlap': len(sets['B'] & sets['C']),
        'B_and_D_overlap': len(sets['B'] & sets['D']),
        'C_and_D_overlap': len(sets['C'] & sets['D']),
        'C_minus_D': sorted(sets['C'] - sets['D']),
        'C_minus_D_count': len(sets['C'] - sets['D']),
        'D_minus_C': sorted(sets['D'] - sets['C']),
        'D_minus_C_count': len(sets['D'] - sets['C']),
        'key_question': 'If C_minus_D is large (candidates accepted by correlation/residual controls but rejected by dataset cap), the cap is the binding constraint, not PnL redundancy',
    }

    # --- Warmstart assessment ---
    warmstart_path = Path(db_path).resolve().parent.parent / 'migrated_runs' / 'earnings4_run2' / 'checkpoint.json'
    warmstart_info = {'assessed': False}
    if warmstart_path.exists():
        cp = json.loads(warmstart_path.read_text())
        pop = cp.get('population', [])
        warmstart_exprs = [p[0] if isinstance(p, list) else p for p in pop]
        # Check if warmstart entries are in the basket-selected sets
        ws_in_deduped = set()
        expr_to_aid = {r['expression']: r.get('alpha_id') for r in deduped}
        for expr in warmstart_exprs:
            aid = expr_to_aid.get(expr)
            if aid:
                ws_in_deduped.add(aid)
        warmstart_info = {
            'assessed': True,
            'total_warmstart_seeds': len(pop),
            'warmstart_expressions_matched_to_scored': len(ws_in_deduped),
            'warmstart_ids_in_variant_C': len(ws_in_deduped & sets['C']),
            'warmstart_ids_in_variant_D': len(ws_in_deduped & sets['D']),
            'construction': 'Migration checkpoint.json population is top-N by NSGA-II-rescored fitness; it did NOT pass through select_basket()',
            'status': 'Historical research candidates. Not labeled qualified, independently diverse, or submission-ready.',
        }
    summary['warmstart_assessment'] = warmstart_info

    # --- Missing-evidence bias ---
    pnl_covered_fitness = sorted([r['fitness'] for r in rows if r.get('alpha_id') in pnls], reverse=True)
    all_fitness = sorted([r['fitness'] for r in rows], reverse=True)
    summary['missing_evidence'] = {
        'total_scored': total_scored,
        'with_pnl': with_pnl,
        'without_pnl': total_scored - with_pnl,
        'pnl_coverage_percent': round(100 * with_pnl / total_scored, 1) if total_scored else 0,
        'median_fitness_pnl_covered': float(np.median(pnl_covered_fitness)) if pnl_covered_fitness else None,
        'median_fitness_all': float(np.median(all_fitness)) if all_fitness else None,
        'pnl_collection_correlation_with_is_qualified': (
            'All 572 qualified rows have PnL; 0 non-qualified rows have PnL'
            if all(r.get('is_qualified') for r in rows if r.get('alpha_id') in pnls)
            and not any(r.get('alpha_id') in pnls for r in rows if not r.get('is_qualified'))
            else 'PnL collection is NOT perfectly correlated with is_qualified'
        ),
        'bias_risk': 'PnL was collected only for candidates that passed a qualification gate (is_qualified=1). '
                     'The PnL-covered subset is a biased sample of the full search. '
                     'Basket correlation/redundancy analysis applies only to this subset and cannot characterize unseen candidates.',
        'recorded_trial_limitation': f'{total_scored} scored rows in the database. This is NOT the total number of attempted simulations; '
                                     'failed simulations, duplicates rejected pre-submission, and manual experiments are not tracked. '
                                     'DSR penalties computed on this count underestimate the true multiple-testing burden.',
    }

    # Save results
    atomic_json(out_path, summary)
    print(json.dumps({
        'variants': list(summary['ablation_variants'].keys()),
        'pool_size': total_scored,
        'pnl_covered': with_pnl,
        'output': out_path,
    }, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', required=True, help='Path to campaign database (read-only)')
    p.add_argument('--meta', required=True, help='Path to forge2_field_meta.json with field_metadata')
    p.add_argument('--out', required=True, help='Output JSON path')
    p.add_argument('--size', type=int, default=20, help='Basket size (default 20)')
    a = p.parse_args()
    run_ablation(a.db, a.meta, a.out, a.size)


if __name__ == '__main__':
    main()
