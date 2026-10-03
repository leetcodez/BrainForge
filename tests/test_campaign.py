import json,sqlite3,sys
import pytest
import forge2_campaign as campaign
import forge2_config as F2
from forge2_bandit import DatasetBandit

def setup_campaign(tmp_path,monkeypatch):
    monkeypatch.setattr(F2,'CAMPAIGN_ROOT',str(tmp_path))
    monkeypatch.setattr(campaign,'AXES',{'USA_d1':{'region':'USA','delay':1,'weight':1.}})
    cdir=campaign.campaign_dir('USA',1)
    (cdir/'forge2_field_meta.json').write_text(json.dumps({'field_to_dataset':{'f':'d'}}))
    with sqlite3.connect(cdir/'brain_memory.db') as con:
        con.execute('CREATE TABLE alpha_population(id INTEGER PRIMARY KEY,expression TEXT,alpha_id TEXT,sharpe REAL,turnover REAL,fitness REAL,is_qualified INTEGER,failed_checks TEXT)')
        con.execute("INSERT INTO alpha_population VALUES(1,'rank(f)','a',2,.2,1,1,'')")
        con.execute('CREATE TABLE alpha_pnl(alpha_id TEXT,date TEXT,pnl REAL)')
    monkeypatch.setattr(campaign,'CatalogIndex',lambda _:type('Catalog',(),{'fields':{'f':1}})())
    monkeypatch.setattr(campaign,'load_live_operators',lambda _:set())
    monkeypatch.setattr(campaign,'build_vocabulary',lambda *a:{'stats':{}})
    monkeypatch.setattr(sys,'argv',['campaign','--catalog','fixture','--bursts','2'])
    return cdir

def test_whole_campaign_keeps_learning_watermark_and_counts_once(tmp_path,monkeypatch):
    cdir=setup_campaign(tmp_path,monkeypatch)
    monkeypatch.setattr(campaign,'run_burst_subprocess',lambda *a:0)
    campaign.main()
    state=campaign.load_state(cdir)
    assert state['since_rowid']==1 and state['bursts_done']==2
    b=DatasetBandit(cdir/F2.BANDIT_STATE_FILE)
    assert b.arms['d']['a']==b.arms['d']['prior_a']+1

def test_failed_burst_preserves_partial_outcomes_without_advancing_schedule(tmp_path,monkeypatch):
    cdir=setup_campaign(tmp_path,monkeypatch)
    monkeypatch.setattr(campaign,'run_burst_subprocess',lambda *a:1)
    with pytest.raises(RuntimeError):campaign.main()
    state=campaign.load_state(cdir)
    assert state['since_rowid']==1 and state['bursts_done']==0

def test_corrupt_state_is_not_silently_reset(tmp_path):
    (tmp_path/'forge2_campaign_state.json').write_text('{broken')
    with pytest.raises(ValueError):campaign.load_state(tmp_path)
