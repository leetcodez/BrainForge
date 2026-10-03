"""Copy and rescore an EXISTING archive offline; never modify its source DB.
This is an explicit new policy view, not recovery of unrecorded historical state.
No network object is constructed, no BRAIN requests or new simulations occur.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
import numpy as np
import os
import forge2_config as F2
import config
from db_manager import DatabaseManager
from forge2_catalog import CatalogIndex
from forge2_checks import parse_checks,finite
from forge2_expression import field_tokens, BUILTIN_GROUPS
from forge2_factory import PyramidResolver, configure_evidence, apply_config_overrides
from forge2_storage import atomic_json
from forge2_vocabulary import VocabularyBuilder, load_live_operators
from orchestrator import AlphaFactory
from oos_deflation import OOSDeflationEngine


def migrate(source, catalog_path, operators_path, destination, region='USA', delay=1):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Destination must be new or empty; original/live state is never overwritten')
    destination.mkdir(parents=True,exist_ok=True)
    catalog=CatalogIndex(catalog_path);operators=load_live_operators(operators_path)
    if not operators:raise ValueError('Recorded operator metadata is required')
    built=VocabularyBuilder(catalog,region,int(delay),operators).write(destination)
    # Load effective engine policy from the same local vocabulary and overrides,
    # without constructing a network client. Restore process environment after
    # module loading; this migration is a one-shot scoring operation.
    import importlib
    updates={**F2.OVERRIDE_ENV,"WQ_FIELD_CATALOG":str(destination/'data_fields.json'),
             "WQ_SEED_POOL":str(destination/'seed_pool.json'),"WQ_OPERATORS_PATH":str(operators_path)}
    previous={key:os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        importlib.reload(config)
    finally:
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    # Stable copy via SQLite backup also captures committed source WAL state.
    original=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    temporary=destination/'migration.tmp.db'
    copied=sqlite3.connect(temporary)
    try:original.backup(copied)
    finally:original.close();copied.close()
    db=DatabaseManager(str(temporary));db.init_db_sync();db.close_sync()
    con=sqlite3.connect(temporary);con.row_factory=sqlite3.Row
    source_snapshot_hash=hashlib.sha256(temporary.read_bytes()).hexdigest()
    rows=[dict(r) for r in con.execute('SELECT * FROM alpha_population WHERE sharpe IS NOT NULL')]
    checks={r['alpha_id']:json.loads(r['metrics_json']) for r in con.execute('SELECT * FROM alpha_checks')}
    pnl={}
    for aid,date,value in con.execute('SELECT alpha_id,date,pnl FROM alpha_pnl WHERE pnl IS NOT NULL'):
        pnl.setdefault(aid,{})[date]=value
    meta=built['meta']
    for row in rows:
        for token in set(field_tokens(row['expression']))-BUILTIN_GROUPS:
            rec=catalog.fields.get(token)
            if rec:
                meta['field_metadata'][token]={'type':rec.type,'dataset':rec.dataset,'category':rec.category,
                    'subcategory':rec.subcategory,'availability':[list(v) for v in rec.availability],
                    'multiplier':rec.for_axis(region,int(delay),row['universe']).multiplier}
                meta['field_to_dataset'][token]=rec.dataset
    meta_path=destination/'forge2_field_meta.json';atomic_json(meta_path,meta)
    resolver=PyramidResolver(meta_path)
    apply_config_overrides(config,region,delay)
    configure_evidence(config,resolver)
    scorer=AlphaFactory.__new__(AlphaFactory) # no db/network/LLM construction
    scorer.deflation=OOSDeflationEngine()
    config.DEFLATION_MAX_TRIALS=0;config.THIRD_OBJECTIVE_ENABLED=F2.THIRD_OBJECTIVE_ENABLED
    scores=[float(r['sharpe'])/math.sqrt(config.PERIODS_IN_YEAR) for r in rows if math.isfinite(r['sharpe'])]
    variance=float(np.var(scores)) if len(scores)>1 else (0.4/math.sqrt(config.PERIODS_IN_YEAR))**2
    n=max(2,len(rows))
    # Frozen reference basket is part of the migration receipt; do not pretend
    # this reconstructs the original live elite-reference choices.
    refs=sorted(rows,key=lambda r:r.get('fitness') if r.get('fitness') is not None else -float('inf'),reverse=True)[:max(1,int(config.POPULATION_SIZE*config.ELITISM_RATIO))]
    dsrs=[scorer.deflation.calculate_dsr(r['sharpe'],r.get('skew') or 0,r.get('kurtosis') or 0,
             r.get('track_record_length') or config.DEFAULT_TRACK_RECORD_LENGTH,n,variance) for r in rows]
    adjusted=scorer.deflation.calculate_orthogonal_fitness_batch([r['expression'] for r in rows],[r['expression'] for r in refs],dsrs)
    adjusted=scorer.deflation.calculate_return_orthogonal_fitness_batch([pnl.get(r.get('alpha_id')) for r in rows],
             [pnl[r['alpha_id']] for r in refs if r.get('alpha_id') in pnl],adjusted,
             config.RETURN_DECORR_MIN_OVERLAP,config.RETURN_DECORR_K)
    columns={r[1] for r in con.execute('PRAGMA table_info(alpha_population)')}
    if 'legacy_fitness' not in columns:con.execute('ALTER TABLE alpha_population ADD COLUMN legacy_fitness REAL')
    population=[];unknown=0
    with con:
        for row,score in zip(rows,adjusted):
            depth=row.get('ast_depth') or 1
            fitness=scorer._composite_fitness(score,depth,row['sharpe'],row.get('oos_sharpe'),row['expression'])
            evidence=parse_checks(checks.get(row.get('alpha_id'),{}))
            fail=','.join(evidence.failed) if evidence.verified else 'CHECKS_UNVERIFIABLE'
            unknown+=not evidence.verified
            # Never fabricate readiness from old headline metrics. Keep a prior
            # qualification only when raw check evidence still supports it.
            metrics=checks.get(row.get('alpha_id'),{})
            min_fitness=config.MIN_FITNESS_DELAY0 if int(delay)==0 else config.MIN_FITNESS
            corr=finite(row.get('max_correlation'))
            drawdown=finite(metrics.get('drawdown'));margin=finite(metrics.get('margin'))
            risk=(not config.DRAWDOWN_MARGIN_GATE_ENABLED or
                  ((config.MAX_DRAWDOWN is None or (drawdown is not None and abs(drawdown)<=config.MAX_DRAWDOWN))
                   and (config.MIN_MARGIN is None or (margin is not None and margin>=config.MIN_MARGIN))))
            qualified=int(bool(row.get('is_qualified') and evidence.verified and not evidence.failed
                       and row['sharpe']>=config.MIN_SHARPE
                       and config.MIN_TURNOVER<=row['turnover']<=config.MAX_TURNOVER
                       and config.worldquant_fitness(row['sharpe'],row.get('returns') or 0,row['turnover'])>=min_fitness
                       and corr is not None and 0<=corr<=config.MAX_SELF_CORRELATION and risk))
            con.execute('UPDATE alpha_population SET legacy_fitness=fitness,fitness=?,is_qualified=?,failed_checks=? WHERE id=?',
                        (fitness,qualified,fail,row['id']))
            valid,_=catalog.validate_expression(row['expression'],region,int(delay),row['universe'])
            if valid:
                population.append({**row,'fitness':fitness,'expected_value':max(0,config.worldquant_fitness(row['sharpe'],row.get('returns') or 0,row['turnover']))*resolver.boost(row['expression'],row['universe'])})
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    # Move the committed copy only. No connection ever writes to `source`.
    final_db=destination/'brain_memory.db';temporary.replace(final_db)
    population=scorer._nsga_ii_sort(population)[:config.POPULATION_SIZE]
    atomic_json(destination/'checkpoint.json',{'generation':0,'submission_count':0,
                'population':[[r['expression'],r['universe'],r['decay']] for r in population]})
    atomic_json(destination/'forge2_campaign_state.json',{'bursts_done':0,'since_rowid':0})
    from forge2_policy import fingerprint
    atomic_json(destination/'forge2_run_policy.json',fingerprint(config,catalog.catalog_hash,operators_path))
    manifest_path=destination/'forge2_epoch_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    epoch_dir=destination/manifest['epoch_dir']
    atomic_json(epoch_dir/'forge2_field_meta.json',json.loads((destination/'forge2_field_meta.json').read_text()))
    manifest['files']['forge2_field_meta.json']=hashlib.sha256((epoch_dir/'forge2_field_meta.json').read_bytes()).hexdigest()
    atomic_json(manifest_path,manifest)
    receipt={'source_snapshot_sha256':source_snapshot_hash,'source':str(source),'destination':str(final_db),'rescored_rows':len(rows),
             'unknown_check_rows':unknown,'warmstart_members':len(population),'fitness_policy':F2.FITNESS_POLICY_VERSION,
             'reference_alpha_ids':[r.get('alpha_id') for r in refs],'uncapped_recorded_trials':len(rows),
             'assumptions':['Stored moments use existing engine conventions; missing moments fall back to existing defaults.',
                            'Frozen reference basket is a new scoring view, not a reconstruction of original live shaping.',
                            'Generation restarts at zero for this explicit offline policy migration; source checkpoints are unchanged.',
                            'Historical check evidence is not fresh platform certification.']}
    atomic_json(destination/'migration_receipt.json',receipt)
    return receipt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db',required=True);ap.add_argument('--catalog',required=True)
    ap.add_argument('--operators',default=F2.OPERATORS_PATH);ap.add_argument('--out',required=True)
    ap.add_argument('--region',default='USA');ap.add_argument('--delay',type=int,default=1)
    a=ap.parse_args();print(json.dumps(migrate(a.db,a.catalog,a.operators,a.out,a.region,a.delay),indent=2))

if __name__=='__main__':main()
