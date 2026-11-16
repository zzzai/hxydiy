"""Scheduling boundaries preserve completed work and stop unknown outcomes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runner
from contracts import Stop
from finance_schedule import scheduled_sync, query_dates, verify_evidence, FILES


def test_blocked_run_never_reads_or_retries(tmp_path):
    runner.save(tmp_path/'state.json', {'blocked':True,'run_id':'prior'})
    def forbidden(*args):raise AssertionError('unexpected work')
    result=scheduled_sync(tmp_path,None,card_sync=forbidden,finance_sync=forbidden,prepare=forbidden)
    assert result['status']=='blocked_latched' and result['model_calls']==0


def test_finance_failure_preserves_card_result_and_latches(tmp_path):
    runner.save(tmp_path/'state.json', {'blocked':False})
    sent=[]
    def fail(*args):raise Stop('finance_page_incomplete')
    result=scheduled_sync(tmp_path,None,prepare=lambda _:None,
        card_sync=lambda *a:{'status':'completed_and_verified','new_cards':2,'run_id':'cards'},
        finance_sync=fail,notify=lambda _:sent.append(True))
    assert result['cards']['new_cards']==2 and 'business_writes' not in result
    assert result['status']=='blocked' and result['code']=='finance_page_incomplete'
    assert json.loads((tmp_path/'state.json').read_bytes())['blocked'] is True
    again=scheduled_sync(tmp_path,None,prepare=fail,notify=lambda _:sent.append(True))
    assert again['status']=='blocked_latched' and len(sent)==1


def test_success_contains_both_stages(tmp_path):
    runner.save(tmp_path/'state.json', {'blocked':False})
    result=scheduled_sync(tmp_path,None,prepare=lambda _:None,
        card_sync=lambda *a:{'status':'no_new','run_id':'cards'},
        finance_sync=lambda *a:{'status':'applied_verified','run_id':'finance','old_data_unchanged':True})
    assert result['status']=='completed_and_verified' and result['finance']['run_id']=='finance'
    assert json.loads((tmp_path/'state.json').read_bytes())['blocked'] is False


def test_query_dates_cover_history_and_current_minute():
    histories={'x':{'pages':[{'rows':[{'time':'2025-12-31 23:59:59'}]}]}}
    assert query_dates(histories,datetime(2026,1,1,0,0,20,tzinfo=timezone.utc))==['2025-12-31 00:00','2026-01-01 08:01']
    with pytest.raises(Stop):query_dates({'x':{'pages':[{'rows':[{'time':'unknown'}]}]}},datetime.now(timezone.utc))


def test_incomplete_and_stale_sources_never_reach_server(tmp_path):
    now=datetime(2026,11,16,5,tzinfo=timezone.utc)
    with pytest.raises(Stop):verify_evidence(tmp_path,now)
    for name in FILES:
        runner.save(tmp_path/name,{'status':'collected_unverified','business_writes':0,'observed_at':'2026-11-15T00:00:00+00:00'})
    with pytest.raises(Stop):verify_evidence(tmp_path,now)


def test_invalid_finance_result_is_not_success(tmp_path):
    runner.save(tmp_path/'state.json', {'blocked':False})
    result=scheduled_sync(tmp_path,None,prepare=lambda _:None,
        card_sync=lambda *a:{'status':'no_new'},finance_sync=lambda *a:{'status':'prepared'},notify=lambda _:None)
    assert result['status']=='blocked' and json.loads((tmp_path/'state.json').read_bytes())['blocked']


def test_zero_candidate_preview_keeps_conflict_guard():
    from finance_schedule import empty_preview
    value={'status':'no_new','business_writes':0,'insert_bills':0,'insert_lines':0,'insert_balances':0,'conflicting_bill_groups':0}
    assert empty_preview(value)
    with pytest.raises(Stop):empty_preview(dict(value,conflicting_bill_groups=1))
    with pytest.raises(Stop):empty_preview(dict(value,insert_balances=1))
    assert not empty_preview(dict(value,status='preview',insert_balances=1))


def test_server_prior_failure_prevents_compile_or_apply(tmp_path,monkeypatch):
    import finance_server
    agent=tmp_path/'agent';agent.mkdir()
    prior={'blocked':True,'run_id':'unresolved','business_outcome':'unknown'}
    runner.save(agent/'server-state.json',prior)
    monkeypatch.setattr(finance_server,'AGENT',agent)
    root=tmp_path/'batch';root.mkdir()
    with pytest.raises(Stop,match='server_failure_latched'):
        finance_server.process(root,'new','0'*64)
    assert json.loads((agent/'server-state.json').read_bytes())==prior
    assert list(root.iterdir())==[]


def test_bad_upload_never_marks_attempt_or_touches_database(tmp_path,monkeypatch):
    import finance_server
    agent=tmp_path/'agent';agent.mkdir();runner.save(agent/'server-state.json',{'blocked':False})
    monkeypatch.setattr(finance_server,'AGENT',agent)
    root=tmp_path/'batch';root.mkdir();runner.save(root/'upload-sha256.json',{})
    with pytest.raises(Stop,match='finance_upload_manifest_changed'):
        finance_server.process(root,'new','0'*64)
    assert not (root/'attempt.json').exists()
    assert json.loads((agent/'server-state.json').read_bytes())=={'blocked':False}


def test_fresh_complete_source_and_future_source(tmp_path):
    now=datetime(2026,11,16,5,tzinfo=timezone.utc)
    value={'status':'collected_unverified','business_writes':0,'observed_at':'2026-11-16T04:59:00+00:00'}
    for name in FILES:runner.save(tmp_path/name,value)
    verify_evidence(tmp_path,now)
    runner.save(tmp_path/FILES[0],dict(value,observed_at='2026-11-16T05:00:01+00:00'))
    with pytest.raises(Stop,match='finance_observation_expired'):verify_evidence(tmp_path,now)


def test_card_failure_never_starts_finance(tmp_path):
    runner.save(tmp_path/'state.json',{'blocked':False})
    def forbidden(*args):raise AssertionError('finance must not run')
    result=scheduled_sync(tmp_path,None,prepare=lambda _:None,card_sync=lambda *a:{'status':'blocked','run_id':'card-error'},finance_sync=forbidden)
    assert result=={'status':'blocked','run_id':'card-error'}
