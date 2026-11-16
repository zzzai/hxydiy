"""Sequential ordinary-code scheduling, with durable stop on every unresolved stage."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import uuid

from contracts import Stop, require
import runner

FILES=('collection-pass1.json','collection-pass2.json','ledger-pass1.json','payments-pass1.json')
TZ=timezone(timedelta(hours=8))


def query_dates(histories, now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(TZ)
    dates=[]
    for history in histories.values():
        for page in history['pages']:
            for row in page['rows']:
                value=row.get('time')
                require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?',value),'finance_history_time_invalid')
                parsed=datetime.fromisoformat(value).replace(tzinfo=TZ)
                require(parsed<=now,'finance_history_time_future')
                dates.append(parsed)
    start=min(dates,default=now).replace(hour=0,minute=0,second=0,microsecond=0)
    end=now.replace(second=0,microsecond=0)+timedelta(minutes=1)
    return [start.strftime('%Y-%m-%d %H:%M'),end.strftime('%Y-%m-%d %H:%M')]


def verify_evidence(source, now=None):
    now=now or datetime.now(timezone.utc)
    for name in FILES:
        path=Path(source)/name
        require(path.is_file() and not path.is_symlink(),'finance_evidence_missing')
        value=json.loads(path.read_bytes())
        require(value.get('status')=='collected_unverified' and value.get('business_writes')==0,'finance_collection_incomplete')
        observed=datetime.fromisoformat(value['observed_at'])
        require(observed.tzinfo is not None and 0<=(now-observed).total_seconds()<=7200,'finance_observation_expired')


def scheduled_sync(root,page,card_sync=None,finance_sync=None,prepare=None,notify=None):
    root=Path(root)
    state=json.loads((root/'state.json').read_bytes()) if (root/'state.json').exists() else {}
    if state.get('blocked') is True:
        return {'status':'blocked_latched','run_id':state.get('run_id'),'model_calls':0,'business_writes':0}
    report={'model_calls':0,'mode':'controlled_membership_and_finance'}
    try:
        if prepare is None:
            from financial_ui import member_query
            from source_login import ensure_login
            def prepare(page):
                ensure_login(page,root)
                member_query(page)
        prepare(page)
        if card_sync is None:
            from bridge import sync_once
            from collector import Collector
            card_sync=lambda root,page:sync_once(root,lambda keys:Collector(page,keys).collect())
        report['cards']=card_sync(root,page)
        if report['cards']['status'] not in ('no_new','completed_and_verified'):
            return report['cards']
        if finance_sync is None:
            from finance_bridge import sync_finance
            finance_sync=sync_finance
        report['finance']=finance_sync(root,page)
        require(report['finance']['status'] in ('applied_verified','no_new'),'finance_outcome_not_verified')
        report.update(status='completed_and_verified',run_id=report['finance']['run_id'])
        runner.save(root/'report.json',report)
        runner.save(root/'state.json',{'blocked':False,'last_success':report['run_id'],
                    'mode':report['mode'],'apply_enabled':True})
        return report
    except Exception as exc:
        report.update(status='blocked',code=str(exc) if isinstance(exc,Stop) else 'scheduled_finance_failed_no_retry',
                      exception_type=type(exc).__name__,business_outcome='inspect_completed_stages_and_exact_receipts')
        current=json.loads((root/'state.json').read_bytes()) if (root/'state.json').exists() else {}
        report['run_id']=current.get('run_id',report.get('cards',{}).get('run_id'))
        runner.save(root/'state.json',dict(report,blocked=True))
        runner.save(root/'report.json',report)
        (notify or runner.notify)(root)
        return report


def empty_preview(value):
    require(value.get('status') in ('preview','no_new') and value.get('business_writes')==0,'finance_preview_not_readonly')
    require(value.get('conflicting_bill_groups')==0,'finance_revision_conflict')
    counts=[value.get(k) for k in ('insert_bills','insert_lines','insert_balances')]
    require(all(type(n) is int and n>=0 for n in counts),'finance_preview_counts_invalid')
    empty=not any(counts)
    require(value['status']!='no_new' or empty,'finance_no_new_count_mismatch')
    return empty
