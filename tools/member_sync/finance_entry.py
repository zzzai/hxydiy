"""Private, hash-bound finance import entry; invoked by the controlled host runner."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys


def digest(path):return sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['baseline','preview','snapshot-check','rehearse','apply','verify'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--database',required=True)
    parser.add_argument('--runtime-sha',required=True)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--recovery-sha')
    args=parser.parse_args();root=args.root.resolve();os.umask(0o077)
    if root.is_symlink() or root.stat().st_mode&0o077:raise ValueError('private_root_required')
    if not re.fullmatch(r'[a-f0-9]{64}',args.runtime_sha) or digest(root/'runtime-index.json')!=args.runtime_sha:raise ValueError('runtime_index_mismatch')
    index=json.loads((root/'runtime-index.json').read_bytes())
    for name,expected in index.items():
        if Path(name).name!=name or digest(root/name)!=expected:raise ValueError('runtime_file_mismatch')
    if Path(__file__).resolve().parent!=root:raise ValueError('entry_path_mismatch')
    # Load only the reviewed new service from this private batch, without changing /app.
    import app.services
    app.services.__path__.insert(0,str(root))
    from app.db.session import engine
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import sessionmaker
    from app.models import User,MembershipConsumptionBatch,MembershipConsumptionBill,MembershipBalanceSnapshot
    from app.services.member_financial_import import execute,packet_sha256
    from app.services.customer_consumption import build_customer_consumption_history
    from app.services.customer_membership import build_customer_membership_overview
    from member_finance_guard import Protection,snapshot,fingerprint,APPEND_TABLES
    from finance_packet import compile_packet,decode_packet,encode_packet
    packet=decode_packet(json.loads((root/'packet.json').read_bytes()))
    if packet.manifest_sha256!=args.manifest or packet_sha256(packet)!=args.manifest:raise ValueError('manifest_mismatch')
    rebuilt,source_index,_=compile_packet(root/'source',packet.batch_key)
    if encode_packet(packet)!=encode_packet(rebuilt):raise ValueError('source_packet_mismatch')
    if json.loads((root/'source-index.json').read_bytes())!=source_index:raise ValueError('source_index_mismatch')
    if args.database!='hxy_diy' and not re.fullmatch(r'hxy_diy_rehearsal_finance_[a-f0-9]{12}(?:_[a-f0-9]{8})?',args.database):raise ValueError('database_outside_scope')
    if args.mode=='rehearse' and args.database=='hxy_diy':raise ValueError('rehearsal_must_be_isolated')
    if args.mode in ('baseline','preview','apply') and args.database!='hxy_diy':raise ValueError('production_mode_database_mismatch')
    target=create_engine(engine.url.set(database=args.database),pool_pre_ping=True)
    sessions=sessionmaker(target,autoflush=False,expire_on_commit=False)
    with sessions() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        identity=dict(db.execute(text("SELECT current_database() AS database,current_schema() AS schema,current_user AS role,(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,pg_postmaster_start_time()::text AS postmaster_started_at")).mappings().one())
        state=snapshot(db)
    base={'manifest_sha256':args.manifest,'input_sha256':digest(root/'packet.json'),'runtime_sha256':args.runtime_sha,
          'database_identity':identity,'snapshot_sha256':fingerprint(state),'created_at':datetime.now(timezone.utc).isoformat()}
    if args.mode=='baseline':
        save(root/'baseline-private.json',state);save(root/'baseline.json',base)
        print(json.dumps(dict(base,status='baseline_frozen',business_writes=0)));return
    baseline=json.loads((root/'baseline-private.json').read_bytes());baseline_meta=json.loads((root/'baseline.json').read_bytes())
    if fingerprint(baseline)!=baseline_meta['snapshot_sha256']:raise ValueError('baseline_file_mismatch')
    if args.mode=='snapshot-check':
        if state!=baseline:raise ValueError('snapshot_changed')
        print(json.dumps(dict(base,status='snapshot_matches',business_writes=0)));return
    if args.mode=='verify':
        for name,old in baseline.items():
            if (name not in APPEND_TABLES and state[name]!=old) or (name in APPEND_TABLES and Counter(old)-Counter(state[name])):raise ValueError('old_data_protection_failed')
        replay=execute(sessions,packet)
        if replay['status']!='already_applied' or replay['business_writes']!=0:raise ValueError('replay_not_zero')
        with sessions() as db:
            batch=db.scalar(select(MembershipConsumptionBatch).where(MembershipConsumptionBatch.batch_key==packet.batch_key))
            if batch is None:raise ValueError('batch_missing')
            bills=db.scalars(select(MembershipConsumptionBill).where(MembershipConsumptionBill.batch_id==batch.id)).all()
            balances=db.scalars(select(MembershipBalanceSnapshot).where(MembershipBalanceSnapshot.source_batch_id==batch.id)).all()
            if len(bills)!=len(packet.bills) or len(balances)!=len(packet.balances):raise ValueError('actual_count_mismatch')
            phones={x.phone for x in packet.bills}|{x.phone for x in packet.balances}
            users=db.scalars(select(User).where(User.phone.in_(phones))).all()
            visible=0
            for user in users:
                history=build_customer_consumption_history(db,user,limit=5000)
                expected={b.source_bill_no for b in bills if b.user_id==user.id}
                actual={b['source_bill_no'] for b in history['bills']}
                if actual!=expected or history['savings']['amount_cents'] is not None:raise ValueError('customer_history_projection_mismatch')
                visible+=len(actual)
                overview=build_customer_membership_overview(db,user)
                by_card={c["id"]:c for c in overview["cards"]}
                for balance in balances:
                    if balance.card_id in by_card:
                        display=by_card[balance.card_id]["balance"]
                        if display["amount_cents"]!=balance.total_cents or display["evidence"]!="balance_snapshot" or display["observed_at"] is None:raise ValueError("customer_balance_projection_mismatch")
            other=db.scalar(select(User).where(User.phone.not_in(phones)).order_by(User.id))
            if other is not None and build_customer_consumption_history(db,other)["bills"]:raise ValueError("other_customer_history_leak")
        print(json.dumps(dict(base,status='verified',old_data_unchanged=True,insert_bills=len(bills),insert_balances=len(balances),visible_owned_bills=visible,replay_business_writes=0,savings_status='unverified')));return
    if args.mode=='apply':
        if not args.recovery_sha or digest(root/'recovery.json')!=args.recovery_sha:raise ValueError('recovery_sha_mismatch')
        recovery=json.loads((root/'recovery.json').read_bytes())
        if recovery['manifest_sha256']!=args.manifest or recovery['runtime_sha256']!=args.runtime_sha or recovery['baseline_sha256']!=fingerprint(baseline) or recovery['status']!='passed':raise ValueError('recovery_binding_failed')
        if recovery['production_identity']!=identity:raise ValueError('production_identity_changed')
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(recovery['completed_at'])).total_seconds()
        if not 0<=age<=3600:raise ValueError('recovery_evidence_expired')
        save(root/'apply-attempt.json',dict(base,recovery_sha256=args.recovery_sha))
    guard=Protection(baseline,expected={"membership_consumption_batches":1,"membership_consumption_bills":len(packet.bills),
        "membership_consumption_lines":sum(len(x.bill.lines) for x in packet.bills),"membership_balance_snapshots":len(packet.balances)})
    result=execute(sessions,packet,apply=args.mode in ('rehearse','apply'),protection=guard)
    expected='preview' if args.mode=='preview' else 'applied'
    if result['status']!=expected:raise ValueError('unexpected_import_status')
    report=dict(base,**result,protection=guard.result)
    save(root/(args.mode+'-result.json'),report)
    print(json.dumps({k:v for k,v in report.items() if k!='protection'}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Preserve detailed private stderr in the host runner, never print identities.
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__,'detail':str(exc) if type(exc) is ValueError else 'private_diagnostic_required'}))
        raise
