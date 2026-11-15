"""Freeze today's exact candidate evidence using a read-only production transaction."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from sqlalchemy import select, text
from app.models import User, MembershipCard, Store, AuditLog

ROOT = Path(__file__).resolve().parent
RUNNER_SHA = '3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925'
CORE_SHA = '2101c73e3a815eb229dbfa834ed2ab403504ae2d8440ab7162daa82326a17e13'
request = json.loads((ROOT / 'batch-request.json').read_bytes())
KEYSET_SHA = request['source_keyset_sha256']
CARD_COUNT = request['new_cards']
SOURCE_COUNT = request['source_cards']
PRIOR_MANIFEST = request['prior_manifest_sha256']
TZ = timezone(timedelta(hours=8))
FACTS_SHA, CONFIRMATION_SHA = request['facts_sha256'], request['confirmation_sha256']
FINANCIAL = ['membership_benefit_grants', 'order_events', 'orders', 'recharges', 'settlement_adjustments', 'user_coupons']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    content = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    with os.fdopen(os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(content)
    return sha(ROOT / name)

assert sha(ROOT / 'import_member_card_batch.py') == RUNNER_SHA
spec = importlib.util.spec_from_file_location('reviewed_member_batch', ROOT / 'import_member_card_batch.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
assert guard.code_sha256(Path(guard.core.__file__)) == CORE_SHA
assert sha(ROOT / 'source-ui-facts-private.json') == FACTS_SHA
assert sha(ROOT / 'source-status-attestation.json') == CONFIRMATION_SHA
facts = json.loads((ROOT / 'source-ui-facts-private.json').read_bytes())
confirmation = json.loads((ROOT / 'source-status-attestation.json').read_bytes())
assert facts['scope'] == confirmation['scope'] == {'tenant_id':1581452,'shop_id':1581453,'store_id':1,'source':'meiguanjia_export','store_code':'hxy-anyang-ziwei-001'}
assert facts['source_keyset_sha256'] == confirmation['source_keyset_sha256'] == KEYSET_SHA
assert confirmation['confirmation'] == '这个问题 以后不用问了，都是正常的，直接新增即可' and confirmation['user_confirmation_date'] == '2026-10-25'
assert confirmation['applies_only_to_frozen_snapshot'] and confirmation['new_candidates_only']
assert datetime.now(TZ).date().isoformat() == request['verification_date']
keys = [guard.source_key(row['card_number']) for row in facts['rows']]
assert len(keys) == len(set(keys)) == SOURCE_COUNT
assert hashlib.sha256('\n'.join(sorted(keys)).encode()).hexdigest() == KEYSET_SHA
new_rows = [row for row in facts['rows'] if 'phone' in row]
new_keys = {guard.source_key(row['card_number']) for row in new_rows}
assert len(new_rows) == len(new_keys) == CARD_COUNT
assert 0 < CARD_COUNT <= 100
for row in new_rows:
    assert re.fullmatch(r'1[3-9]\d{9}', row['phone'])
    assert row['store_name'] == '紫薇壹号店' and row['allow_cross_store_text'] == '否'
    assert row['card_name'] in {'荷小悦年度权益会员卡', '荷小悦会员卡'} and row['source_card_type'] == '储值消费卡'
    assert row['ownership_evidence'] and row['phone'][:3] + '****' + row['phone'][-4:] == row['masked_phone']
phones = {row['phone'] for row in new_rows}
baseline = {'target_store': {'id':1,'store_code':guard.STORE_CODE},
            'protected_users': {'columns':list(User.__table__.columns.keys())},
            'protected_cards': {'columns':list(MembershipCard.__table__.columns.keys())}}
with guard.core.SessionLocal() as db:
    db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
    db.execute(text("SET LOCAL statement_timeout = '15s'"))
    db.execute(text("SET LOCAL lock_timeout = '5s'"))
    db.execute(text("SET LOCAL work_mem = '4MB'"))
    store = db.get(Store, 1)
    assert store is not None and store.store_code == guard.STORE_CODE
    state = guard.snapshot(db, baseline)
    cards = [dict(row) for row in db.execute(select(MembershipCard.id, MembershipCard.source, MembershipCard.source_card_key, MembershipCard.store_id, MembershipCard.user_id).order_by(MembershipCard.id)).mappings()]
    source_cards = [row for row in cards if row['source'] == guard.SOURCE]
    assert all(row['store_id'] == 1 for row in source_cards)
    assert set(keys) - {row['source_card_key'] for row in source_cards} == new_keys, 'candidate_set_changed'
    assert not new_keys.intersection(row['source_card_key'] for row in source_cards)
    receipts = db.scalars(select(AuditLog).where(AuditLog.action=='member_card_batch_applied', AuditLog.store_id==1, AuditLog.detail['manifest_sha256'].as_string()==PRIOR_MANIFEST)).all()
    assert len(receipts) == 1 and receipts[0].detail['input_sha256'] == request['prior_input_sha256']
    assert set(receipts[0].detail['card_ids']).issubset(row['id'] for row in source_cards)
    matches = db.execute(select(User.id, User.phone).where(User.phone.in_(phones))).all()
    assert len(matches) == len({row.phone for row in matches})
    from continuity import verify_continuity
    continuity_result = verify_continuity(db, guard, ROOT, request, state, phones, new_keys)
    save('continuity-result.json', continuity_result)
    baseline['existing_cards'] = cards
    baseline['protected_users'].update(rows=state['users'], dataset_sha256=guard.fingerprint(state['users']))
    baseline['protected_cards'].update(global_rows=state['cards'], global_dataset_sha256=guard.fingerprint(state['cards']))
    baseline['financial_tables'] = {}
    for name in FINANCIAL:
        hashes = list(db.scalars(text('SELECT md5(row_to_json(t)::text) AS row_hash FROM ' + name + ' AS t ORDER BY row_hash')))
        baseline['financial_tables'][name] = {'rows':len(hashes),'sha256':hashlib.sha256(json.dumps(hashes,separators=(',',':')).encode()).hexdigest()}
    baseline['database_identity'] = guard.database_identity(db)
    baseline['captured_at_utc'] = datetime.now(timezone.utc).isoformat()
    baseline['previous_manifest_audit_count'] = len(receipts)
    new_users = len(phones) - len(matches)
    db.rollback()

precision = {'observed_precision':'date_only','timezone':'UTC+08:00','original_time_of_day':'unknown',
             'epoch_derivation':'visible original YYYY-MM-DD at local midnight; not original source timestamp',
             'reference':'docs/operations/member-card-import.md date-only convention','facts_sha256':FACTS_SHA}
columns = ['card_number','phone','card_name','opened_at_epoch_ms','expires_at_date','principal_yuan','source_card_type','allow_cross_store_text','opened_at_date_original','opening_date_precision']
rows = []
for row in facts['rows']:
    if 'phone' not in row:
        rows.append([row['card_number']] + [None] * (len(columns)-1))
        continue
    opening = row['opened_at_date']
    expiry = row['expires_at_date']
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',opening)
    assert (expiry is None and row['card_name'] == '荷小悦会员卡' and row['source_expiry_unlimited']) or (isinstance(expiry,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',expiry))
    amount = Decimal(row['principal_yuan'])
    assert amount.is_finite() and amount >= 0 and amount*100 == (amount*100).to_integral_value()
    rows.append([row['card_number'],row['phone'],row['card_name'],int(datetime.fromisoformat(opening).replace(tzinfo=TZ).timestamp()*1000),expiry,row['principal_yuan'],row['source_card_type'],row['allow_cross_store_text'],opening,'date_only'])
source = {'source_tenant_id':1581452,'source_shop_id':1581453,'source_total_cards':SOURCE_COUNT,'columns':columns,'rows':rows,
          'source_keyset_sha256':KEYSET_SHA,'opening_date_evidence':precision,'original_source_facts_sha256':FACTS_SHA,'source_status_confirmation_sha256':CONFIRMATION_SHA}
source_sha = save('source-cards.json',source)
batch_id = request['batch_id']
save('bound-attestation.json',{'task_id':batch_id,'verified_status':'active','scope_excludes_future_cards':True,'confirmed_on':request['verification_date'],'user_confirmation_date':'2026-10-25','confirmation_basis':'standing_owner_confirmation_applied_to_current_frozen_snapshot','confirmed_on_semantics':'operator verification date binding standing confirmation to this snapshot; not a new user confirmation',
    'scope':{'cards':SOURCE_COUNT,'tenant_id':1581452,'shop_id':1581453},'source_file_sha256':source_sha,
    'source_rows_sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
    'original_confirmation_sha256':CONFIRMATION_SHA,'source_keyset_sha256':KEYSET_SHA,'opening_date_evidence':precision})
save('candidate-input.json',{'source':guard.SOURCE,'store_code':guard.STORE_CODE,'cards':[guard.project_source(dict(zip(columns,row,strict=True))) for row in rows if guard.source_key(row[0]) in new_keys]})
with os.fdopen(os.open(ROOT/'candidate-phones.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
    stream.write('\n'.join(sorted(phones))+'\n')
save('baseline-private.json',baseline)
names = {'source':'source-cards.json','attestation':'bound-attestation.json','input':'candidate-input.json','phones':'candidate-phones.txt','baseline':'baseline-private.json'}
manifest = {'version':1,'batch_id':batch_id,'source':guard.SOURCE,'store_id':1,'store_code':guard.STORE_CODE,'cards':CARD_COUNT,'people':len(phones),'new_users':new_users,
            'new_source_keys':sorted(new_keys),'runner_sha256':RUNNER_SHA,'core_sha256':CORE_SHA,'files':{role:{'name':name,'sha256':sha(ROOT/name)} for role,name in names.items()}}
manifest_sha = save('candidate-manifest.json',manifest)
guard.load_batch(ROOT/'candidate-manifest.json',manifest_sha)
summary = {'status':'prepared_and_load_batch_validated','manifest_sha256':manifest_sha,'input_sha256':sha(ROOT/'candidate-input.json'),
           'new_cards':CARD_COUNT,'new_users':new_users,'people':len(phones),'existing_user_matches':len(matches),'protected_users':len(state['users']),
           'protected_cards':len(state['cards']),'target_only_source_cards':len({r['source_card_key'] for r in source_cards}-set(keys)),'business_writes':0,'apply_executed':False}
save('preparation-summary.json',summary)
print(json.dumps(summary,sort_keys=True))
