import datetime,hashlib,json
import numpy as np
import pytest
from db_manager import DatabaseManager
from forge2_quant_review import review_archives,assess_return_panel


def test_quant_archive_review_is_readonly_and_never_converts_pnl_into_returns(tmp_path):
    path=tmp_path/'archive.db';db=DatabaseManager(str(path));db.init_db_sync()
    db.save_alpha_sync('rank(f)','U',0,'a',0,2,.2,1,4,returns=.1)
    db.close_sync();before=hashlib.sha256(path.read_bytes()).hexdigest()
    report=review_archives([path])
    assert len(report['baskets'])==1 and not report['baskets'][0]['diversity']['verified']
    assert 'normalization' in report['scope']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def panel():
    rng=np.random.default_rng(45)
    return {'metadata':{'unit':'daily_arithmetic_excess_return','calendar':'trading_day','capital_normalization':'verified',
                        'cost_basis':'net','excess_return_reference':'recorded_cash_rate','previously_viewed':True},
            'observations':[{'date':(datetime.date(2020,1,1)+datetime.timedelta(days=i)).isoformat(),
                            'values':{'a':float(rng.normal(.001,.01))}} for i in range(800)]}


def test_return_inference_refuses_unknown_units_and_never_reads_holdout_for_metrics():
    p=panel();a=assess_return_panel(p,resamples=200)
    assert not a['holdout_evaluated'] and a['previously_viewed']
    for row in p['observations'][a['plan']['holdout'][0]:]:row['values']['a']=99999
    assert assess_return_panel(p,resamples=200)['diagnostics']==a['diagnostics']
    p['metadata']['capital_normalization']='unknown'
    with pytest.raises(ValueError):assess_return_panel(p,resamples=200)
