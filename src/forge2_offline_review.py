"""Read-only review of EXISTING campaign results; no network or credentials.
python forge2_offline_review.py --db campaigns/USA_d1/brain_memory.db --out review.json
Historical gates are not a fresh platform-readiness certificate.
"""
from __future__ import annotations
import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from forge2_checks import parse_checks, finite
from forge2_storage import atomic_json


def review_databases(paths):
    candidates={};status_counts=Counter();scored=0
    for source in map(Path,paths):
        if not source.is_file():raise FileNotFoundError(source)
        meta_path=source.parent/'forge2_field_meta.json'
        axes=json.loads(meta_path.read_text()).get('axes',{}) if meta_path.exists() else {}
        conn=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
        conn.row_factory=sqlite3.Row
        try:
            rows=conn.execute('SELECT * FROM alpha_population WHERE fitness IS NOT NULL AND sharpe IS NOT NULL').fetchall()
            try:checks={r['alpha_id']:json.loads(r['metrics_json']) for r in conn.execute('SELECT * FROM alpha_checks')}
            except sqlite3.OperationalError:checks={}
        finally:conn.close()
        for row in rows:
            scored+=1;raw=dict(row);metrics=checks.get(raw.get('alpha_id'),{})
            evidence=parse_checks(metrics)
            corr=finite(raw.get('max_correlation'))
            if not evidence.verified or corr is None:
                status='unverifiable'
            elif evidence.failed or not raw.get('is_qualified') or corr>.70:
                status='recorded_gate_fail'
            else:status='recorded_gate_pass'
            status_counts[status]+=1
            sharpe=finite(metrics.get('sharpe',raw.get('sharpe')))
            turnover=finite(metrics.get('turnover',raw.get('turnover')))
            returns=finite(metrics.get('returns',raw.get('returns')))
            platform_fit=finite(metrics.get('fitness'))
            if platform_fit is None and None not in (sharpe,turnover,returns):
                platform_fit=sharpe*math.sqrt(abs(returns)/max(turnover,.125))
            value=(platform_fit or 0)*(evidence.pyramid_multiplier or 1)
            record={'expression':raw['expression'],'universe':raw['universe'],'decay':raw['decay'],
                    'region':axes.get('region'),'delay':axes.get('delay'),'alpha_id':raw.get('alpha_id'),
                    'status':status,'internal_fitness':finite(raw.get('fitness')),
                    'platform_fitness':platform_fit,'utility_proxy':value,
                    'pyramid_multiplier':evidence.pyramid_multiplier,
                    'sharpe_2y':evidence.sharpe_2y,'pnl_realization':evidence.pnl_realization,
                    'failed':evidence.failed,'warnings':evidence.warnings,'unknown_checks':evidence.unknown,
                    'source':str(source)}
            context=(axes.get('region'),axes.get('delay')) if axes else (str(source.resolve()),None)
            key=(*context,raw['expression'],raw['universe'],raw['decay'])
            previous=candidates.get(key)
            if previous is None or record['utility_proxy']>previous['utility_proxy']:candidates[key]=record
    order={'recorded_gate_pass':0,'unverifiable':1,'recorded_gate_fail':2}
    ranked=sorted(candidates.values(),key=lambda r:(order[r['status']],-r['utility_proxy']))
    return {'scope':'historical recorded evidence only; no BRAIN calls or fresh submission certification',
            'scored_rows':scored,'unique_candidates':len(ranked),'statuses':dict(status_counts),'candidates':ranked}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db',action='append',required=True)
    ap.add_argument('--out',default='forge2_offline_review.json')
    a=ap.parse_args();report=review_databases(a.db);atomic_json(a.out,report)
    print(json.dumps({k:v for k,v in report.items() if k!='candidates'},indent=2))

if __name__=='__main__':main()
