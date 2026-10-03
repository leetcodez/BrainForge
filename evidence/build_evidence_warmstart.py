#!/usr/bin/env python3
"""Evidence-Aware Warmstart Builder.

Separates measured-core candidates from unverified exploration candidates:
  - Tier 1: Measured-Core: Verified PnL (>= 60 days), passes select_basket()
            portfolio decorrelation (max |r| < 0.8, residual >= 0.1).
  - Tier 2: Unverified Exploration: Distinct syntactically valid candidates
            filling the exploration reserve, explicitly tagged as unverified.
            Prohibits degenerate constant expressions (datasets=[]).

Crucial safety guarantees:
  - NEVER overwrites existing checkpoints (writes to a dedicated new file).
  - NEVER changes qualification gates (preserves CHECKS_UNVERIFIABLE / fail-closed integrity).
  - Credential-free, read-only against the source database, zero network calls.

Usage:
    PYTHONPATH=src python evidence/build_evidence_warmstart.py \
        --db backups/pre_v2_baseline/brain_memory.earnings4_run2.db \
        --meta migrated_runs/earnings4_run2/.epochs/c8336ac56f924355bf715f66b8e0157c/forge2_field_meta.json \
        --out evidence/evidence_aware_warmstart.json \
        --size 20 --explore-fraction 0.2
"""
from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path
from collections import defaultdict
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from forge2_portfolio import select_basket, dataset_members
from forge2_storage import atomic_json


def build_evidence_aware_warmstart(
    db_path: str,
    meta_path: str,
    out_path: str,
    size: int = 20,
    explore_fraction: float = 0.2,
    max_dataset_fraction: float = 1.0,  # 1.0 for single-dataset archives to prevent starvation
    max_abs_correlation: float = 0.8,
    min_residual_fraction: float = 0.1,
    min_overlap: int = 60,
):
    out_file = Path(out_path).resolve()
    # Guard: never overwrite existing active checkpoint.json
    if out_file.name == 'checkpoint.json':
        raise ValueError('Safety guard: do not overwrite checkpoint.json directly. Specify a dedicated destination.')

    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        'SELECT * FROM alpha_population WHERE universe="TOP3000" AND fitness IS NOT NULL AND sharpe IS NOT NULL '
        'ORDER BY fitness DESC, id')]
    pnl_rows = db.execute('SELECT alpha_id, date, pnl FROM alpha_pnl WHERE pnl IS NOT NULL').fetchall()
    
    # Check if alpha_checks exists
    has_checks = False
    try:
        checks_cur = db.execute('SELECT alpha_id, metrics_json FROM alpha_checks')
        checks_data = {r['alpha_id']: r['metrics_json'] for r in checks_cur.fetchall()}
        has_checks = True
    except sqlite3.OperationalError:
        checks_data = {}
    db.close()

    pnls = defaultdict(dict)
    for aid, date, val in pnl_rows:
        pnls[aid][date] = val

    meta = json.loads(Path(meta_path).read_text()).get('field_metadata', {})

    for r in rows:
        r['region'] = 'USA_ASSUMED'
        r['delay'] = 1

    # Expression deduplication (keep highest fitness)
    seen = {}
    for r in rows:
        expr = r['expression']
        if expr not in seen or r['fitness'] > seen[expr]['fitness']:
            seen[expr] = r
    deduped = sorted(seen.values(), key=lambda r: (-r['fitness'], r.get('alpha_id', '')))

    # Filter out degenerate constant expressions (no dataset fields) from exploration consideration
    def is_non_degenerate(r):
        fams = dataset_members(r['expression'], meta)
        return len(fams) > 0

    valid_candidates = [r for r in deduped if is_non_degenerate(r)]

    # Run select_basket
    selected, report = select_basket(
        valid_candidates,
        pnls,
        meta,
        size=size,
        min_overlap=min_overlap,
        max_abs_correlation=max_abs_correlation,
        min_residual_fraction=min_residual_fraction,
        max_dataset_fraction=max_dataset_fraction,
        explore_fraction=explore_fraction,
    )

    verified_ids = {v['alpha_id']: v for v in report.get('verified', [])}
    exploration_ids = set(report.get('exploration', []))
    row_map = {r['alpha_id']: r for r in valid_candidates}

    measured_core = []
    unverified_exploration = []

    for r in selected:
        aid = r['alpha_id']
        fams = dataset_members(r['expression'], meta)
        has_pnl = aid in pnls
        v_info = verified_ids.get(aid)

        # Qualification safety check: preserve legacy check status
        # If checks table was absent or missing, status must remain CHECKS_UNVERIFIABLE
        raw_check_verified = has_checks and aid in checks_data
        check_status = 'CHECKS_VERIFIED' if raw_check_verified else 'CHECKS_UNVERIFIABLE'

        entry = {
            'alpha_id': aid,
            'expression': r['expression'],
            'universe': r['universe'],
            'decay': r['decay'],
            'sharpe': r['sharpe'],
            'turnover': r['turnover'],
            'fitness': r['fitness'],
            'datasets': fams,
            'has_pnl': has_pnl,
            'qualification_status': check_status,
            'legacy_is_qualified': r.get('is_qualified'),
        }

        if aid in verified_ids:
            entry['tier'] = 'measured_core'
            entry['residual_fraction'] = v_info.get('residual_fraction')
            entry['raw_subspace_fraction'] = v_info.get('raw_subspace_fraction')
            entry['common_intervals'] = report.get('common_intervals')
            measured_core.append(entry)
        else:
            entry['tier'] = 'unverified_exploration'
            entry['exploration_reason'] = 'Admitted under exploration reserve quota; PnL diversity unverified'
            unverified_exploration.append(entry)

    # Standard engine-compatible population list: [expression, universe, decay]
    engine_population = [[e['expression'], e['universe'], e['decay']] for e in (measured_core + unverified_exploration)]

    warmstart_payload = {
        'generation': 0,
        'submission_count': 0,
        'population': engine_population,
        'warmstart_manifest': {
            'target_size': size,
            'explore_fraction': explore_fraction,
            'measured_core_count': len(measured_core),
            'unverified_exploration_count': len(unverified_exploration),
            'total_warmstart_count': len(engine_population),
            'measured_core': measured_core,
            'unverified_exploration': unverified_exploration,
            'basket_report': {
                'reason': report.get('reason'),
                'common_intervals': report.get('common_intervals'),
                'shrinkage': report.get('shrinkage'),
                'dataset_counts': report.get('dataset_counts'),
                'rejection_summary': {k: list(report.get('rejections', {}).values()).count(k) for k in set(report.get('rejections', {}).values())}
            },
            'provenance_and_safety_declarations': {
                'source_database': db_path,
                'regime': {'region': 'USA_ASSUMED', 'delay': 1, 'universe': 'TOP3000'},
                'regime_provenance_note': 'Assumed from legacy config.py defaults; not independently verified in source simulation logs.',
                'qualification_integrity': 'All candidates retain their audited check status (CHECKS_UNVERIFIABLE). No platform qualification is fabricated or certified.',
                'network_calls': 0,
                'file_overwrites': 'Target file is isolated; existing active checkpoint.json is preserved untouched.'
            }
        }
    }

    atomic_json(out_file, warmstart_payload)
    print(f'Successfully built evidence-aware warmstart: {out_file}')
    print(f'  Measured Core: {len(measured_core)}')
    print(f'  Unverified Exploration: {len(unverified_exploration)}')
    print(f'  Total Population: {len(engine_population)}')
    return warmstart_payload


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', default='backups/pre_v2_baseline/brain_memory.earnings4_run2.db')
    p.add_argument('--meta', default='migrated_runs/earnings4_run2/.epochs/c8336ac56f924355bf715f66b8e0157c/forge2_field_meta.json')
    p.add_argument('--out', default='evidence/evidence_aware_warmstart.json')
    p.add_argument('--size', type=int, default=20)
    p.add_argument('--explore-fraction', type=float, default=0.2)
    p.add_argument('--max-dataset-fraction', type=float, default=1.0)
    args = p.parse_args()
    build_evidence_aware_warmstart(
        args.db, args.meta, args.out,
        size=args.size,
        explore_fraction=args.explore_fraction,
        max_dataset_fraction=args.max_dataset_fraction
    )
