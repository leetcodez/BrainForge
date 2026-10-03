"""Read-only, credential-free review of existing archives/explicit return panels.
Never treats cumulative dollar PnL as capital-normalized excess returns.
CLI: --db archive.db [--db ...] [--returns panel.json] --out review.json
"""
from __future__ import annotations
import argparse,hashlib,json,sqlite3
from pathlib import Path
from collections import defaultdict
from forge2_inference import sharpe_inference,moving_block_sharpe,paired_sharpe_inference,paired_block_sharpe
from forge2_cscv import cscv_fixed_pool
from forge2_protocol import forward_folds
from forge2_portfolio import select_basket
from forge2_storage import atomic_json


def assess_return_panel(panel,min_train=126,test_size=63,gap=20,holdout_size=126,max_lookback=20,label_horizon=1,resamples=500,comparisons=(),cscv_blocks=0):
    metadata=panel.get('metadata',{})
    if (metadata.get('unit')!='daily_arithmetic_excess_return' or metadata.get('calendar')!='trading_day'
        or metadata.get('capital_normalization')!='verified' or metadata.get('cost_basis') not in ('net','gross')
        or not metadata.get('excess_return_reference')):
        raise ValueError('Need explicit return units, trading-day calendar, verified capital normalization, cost basis and excess-return reference')
    rows=panel.get('observations',[]);dates=[r['date'] for r in rows]
    plan=forward_folds(dates,min_train,test_size,gap,holdout_size,label_horizon,max_lookback)
    identifiers=set(rows[0]['values']) if rows else set()
    if not identifiers or any(set(r['values'])!=identifiers for r in rows):raise ValueError('Return panel must have identical explicit candidate columns; do not silently impute/drop rows')
    diagnostics={}
    for aid in sorted(identifiers):
        # No holdout values are used in diagnostic computations. Full artifact
        # identity hashes are provenance, not inferred future performance.
        values=[rows[i]['values'][aid] for fold in plan['folds'] for i in range(*fold['test'])]
        diagnostics[aid]={'hac':sharpe_inference(values),'block_bootstrap':moving_block_sharpe(values,resamples=resamples),
                          'scope':'registered development test blocks for a fixed recorded candidate; not refit-model CV or untouched holdout certification'}
    test_indices=[i for fold in plan['folds'] for i in range(*fold['test'])]
    contrasts=[]
    for left,right in comparisons:
        if left not in identifiers or right not in identifiers:raise ValueError('Comparison IDs absent from panel')
        a=[rows[i]['values'][left] for i in test_indices];b=[rows[i]['values'][right] for i in test_indices]
        contrasts.append({'left':left,'right':right,'hac':paired_sharpe_inference(a,b),
                          'studentized_blocks':paired_block_sharpe(a,b,resamples=resamples)})
    cscv=None
    if cscv_blocks:
        values=[[rows[i]['values'][aid] for aid in sorted(identifiers)] for i in test_indices]
        cscv=cscv_fixed_pool(values,blocks=cscv_blocks)
    return {'plan':plan,'metadata':metadata,'diagnostics':diagnostics,'paired_contrasts':contrasts,'fixed_pool_cscv':cscv,
            'holdout_evaluated':False,'previously_viewed':bool(metadata.get('previously_viewed',True)),
            'caveat':'Unknown historical exposure defaults to previously viewed. Neither HAC nor bootstrap adjusts selection across tried candidates.'}


def review_archives(paths,size=20):
    groups=defaultdict(list);panels=defaultdict(dict);metadata={};sources=[]
    for file in map(Path,paths):
        file=file.resolve()
        if not file.is_file():raise FileNotFoundError(file)
        manifest=file.parent/'forge2_epoch_manifest.json'
        epoch=file.parent
        if manifest.exists():epoch=file.parent/json.loads(manifest.read_text()).get('epoch_dir','.')
        meta_path=epoch/'forge2_field_meta.json'
        meta=json.loads(meta_path.read_text()) if meta_path.exists() else {};axes=meta.get('axes',{})
        metadata.update(meta.get('field_metadata',{}))
        c=sqlite3.connect(file.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
        try:
            records=[dict(r) for r in c.execute('SELECT * FROM alpha_population WHERE fitness IS NOT NULL AND sharpe IS NOT NULL ORDER BY fitness DESC,id')]
            try:pnl_rows=c.execute('SELECT alpha_id,date,pnl FROM alpha_pnl WHERE pnl IS NOT NULL').fetchall()
            except sqlite3.OperationalError:pnl_rows=[]
        finally:c.close()
        pnls=defaultdict(dict)
        for aid,date,value in pnl_rows:pnls[aid][date]=value
        for r in records:
            if not r.get('alpha_id'):continue
            # An unknown region/delay is kept scoped to its source DB, not pooled.
            regime=(axes.get('region',str(file)),axes.get('delay'),r.get('universe'))
            r['region'],r['delay']=regime[:2]
            groups[regime].append(r)
            if r['alpha_id'] in pnls:panels[regime][r['alpha_id']]=pnls[r['alpha_id']]
        sources.append({'database':str(file),'scored_rows':len(records),'pnl_rows':len(pnl_rows),'axes':axes})
    results=[]
    for regime,rows in groups.items():
        # Overlapping mirrors do not duplicate an alpha ID inside a panel.
        unique={}
        for row in rows:
            aid=row['alpha_id']
            if aid not in unique or row['fitness']>unique[aid]['fitness']:unique[aid]=row
        ordered=sorted(unique.values(),key=lambda r:(-r['fitness'],r['alpha_id']))
        selected,diagnostics=select_basket(ordered,panels[regime],metadata,size)
        results.append({'regime':list(regime),'scored_candidates':len(ordered),'selected_alpha_ids':[r['alpha_id'] for r in selected],
                        'diversity':diagnostics,'qualification':'Not evaluated here; basket membership is not platform eligibility'})
    return {'sources':sources,'baskets':results,'scope':'Historical standardized cumulative-PnL interval redundancy; no net-return Sharpe inference without explicit capital normalization'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',action='append',default=[]);p.add_argument('--returns');p.add_argument('--out',required=True)
    p.add_argument('--min-train',type=int,default=126)
    p.add_argument('--test-size',type=int,default=63)
    p.add_argument('--gap',type=int,default=20)
    p.add_argument('--holdout-size',type=int,default=126)
    p.add_argument('--max-lookback',type=int,default=20)
    p.add_argument('--label-horizon',type=int,default=1)
    p.add_argument('--compare',nargs=2,action='append',default=[],metavar=('LEFT','RIGHT'))
    p.add_argument('--cscv-blocks',type=int,default=0)
    a=p.parse_args()
    if (a.compare or a.cscv_blocks) and not a.returns:p.error('Paired/CSCV diagnostics require explicit return panel')
    if not a.db and not a.returns:p.error('Provide existing DB(s) or an explicit normalized return panel')
    report={'archive_review':review_archives(a.db),'return_inference':None,'network_calls':0}
    if a.returns:
        raw=Path(a.returns).read_bytes();report['return_file_sha256']=hashlib.sha256(raw).hexdigest()
        report['return_inference']=assess_return_panel(json.loads(raw),min_train=a.min_train,test_size=a.test_size,gap=a.gap,holdout_size=a.holdout_size,max_lookback=a.max_lookback,label_horizon=a.label_horizon,comparisons=a.compare,cscv_blocks=a.cscv_blocks)
    else:report['return_inference_unavailable']='No verified capital-normalized daily excess-return panel provided; PnL is not silently converted'
    atomic_json(a.out,report)
    print(json.dumps({'databases':len(a.db),'basket_regimes':len(report['archive_review']['baskets']),
                      'holdout_evaluated':False,'network_calls':0}))

if __name__=='__main__':main()
