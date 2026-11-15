"""Validate exact protected rows and finances read-only before/after this batch."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.db.session import engine

ROOT = Path(__file__).resolve().parent
RUNNER_SHA = '3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925'
config = json.loads((ROOT/'execution-config.json').read_bytes())
MANIFEST_SHA = config['manifest_sha256']
RESTORE_DB = config['restore_database']
DATABASE, PHASE = sys.argv[1:]
assert DATABASE in {'hxy_diy',RESTORE_DB} and PHASE in {'before','after'}
assert DATABASE == 'hxy_diy' or PHASE == 'before'
assert hashlib.sha256((ROOT/'import_member_card_batch.py').read_bytes()).hexdigest() == RUNNER_SHA
spec = importlib.util.spec_from_file_location('reviewed_member_batch',ROOT/'import_member_card_batch.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
batch = guard.load_batch(ROOT/'candidate-manifest.json',MANIFEST_SHA)
baseline = batch['baseline']
target = engine if DATABASE == 'hxy_diy' else create_engine(engine.url.set(database=DATABASE),pool_pre_ping=True)
try:
    with Session(target) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL work_mem = '4MB'"))
        state = guard.snapshot(db,baseline)
        guard.check_original_records(state,baseline,exact=PHASE=='before')
        identity = guard.database_identity(db)
        metadata = dict(db.execute(text("SELECT current_database() AS database, current_schema() AS schema, current_user AS role, (SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid, pg_postmaster_start_time()::text AS postmaster_started_at, pg_database_size(current_database()) AS database_bytes")).mappings().one())
        financial = {}
        for name in ['membership_benefit_grants','order_events','orders','recharges','settlement_adjustments','user_coupons']:
            hashes = list(db.scalars(text('SELECT md5(row_to_json(t)::text) AS row_hash FROM '+name+' AS t ORDER BY row_hash')))
            financial[name] = {'rows':len(hashes),'sha256':hashlib.sha256(json.dumps(hashes,separators=(',',':')).encode()).hexdigest()}
        assert financial == baseline['financial_tables'], 'financial_protection_changed'
        receipts = db.scalars(select(guard.AuditLog).where(guard.AuditLog.action=='member_card_batch_applied',guard.AuditLog.store_id==1,guard.AuditLog.detail['manifest_sha256'].as_string()==MANIFEST_SHA)).all()
        expected_users = len(baseline['protected_users']['rows']) + (batch['manifest']['new_users'] if PHASE=='after' else 0)
        expected_cards = len(baseline['protected_cards']['global_rows']) + (batch['manifest']['cards'] if PHASE=='after' else 0)
        assert (len(state['users']),len(state['cards']),len(receipts)) == (expected_users,expected_cards,1 if PHASE=='after' else 0)
        prior = db.scalars(select(guard.AuditLog).where(guard.AuditLog.action=='member_card_batch_applied',guard.AuditLog.store_id==1,guard.AuditLog.detail['manifest_sha256'].as_string()==config['prior_manifest_sha256'])).all()
        assert len(prior) == 1, 'prior_batch_audit_changed'
        if PHASE == 'after':
            candidates = guard.candidate_records(db,batch)
            assert len(candidates) == batch['manifest']['cards'] and {c.source_card_key for c in candidates} == set(batch['manifest']['new_source_keys'])
        if PHASE == 'after':
            post = dict(baseline)
            post['protected_users'] = dict(baseline['protected_users'], rows=state['users'], dataset_sha256=guard.fingerprint(state['users']))
            post['protected_cards'] = dict(baseline['protected_cards'], global_rows=state['cards'], global_dataset_sha256=guard.fingerprint(state['cards']))
            with os.fdopen(os.open(ROOT / 'post-protection-private.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
                json.dump(post, stream, sort_keys=True)
        db.rollback()
    print(json.dumps({'status':'passed','phase':PHASE,'identity':identity,'metadata':metadata,'snapshot_sha256':state['sha256'],
                      'users':len(state['users']),'cards':len(state['cards']),'batch_audit_count':len(receipts),
                      'old_users_and_cards_unchanged':True,'financial_tables_unchanged':True,'read_only':True,'rolled_back':True},sort_keys=True))
finally:
    if target is not engine:
        target.dispose()
