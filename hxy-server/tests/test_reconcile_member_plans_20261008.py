import pytest
from datetime import datetime, timezone
import json
import subprocess
import sys
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import AuditLog, MemberPlan, MembershipCard, Store, User
from scripts.reconcile_member_plans_20261008 import reconcile_member_plans


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Store(id=1, name='Synthetic', store_code='synthetic', address='Synthetic'))
        db.add(User(id=1, openid='synthetic-member'))
        db.flush()
        for i in range(22):
            db.add(MembershipCard(user_id=1, store_id=1, source='synthetic',
                                   source_card_key=str(i), card_type='stored', balance_cents=12345,
                                   started_at=datetime(2026, 9, 1, tzinfo=timezone.utc)))
        for i, code, amount, benefits in [(1, 'annual', 9900, ['周二6.8折', '赠89元项目']),
                                          (2, 'stored', 50000, ['线下退款']),
                                          (3, 'monthly', 49900, ['月卡'])]:
            db.add(MemberPlan(id=i, code=code, name=code, price_cents=amount, benefits=benefits, status='published'))
        db.commit()
        yield db
    engine.dispose()


def snapshot(db, table):
    return [dict(r) for r in db.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings()]


def test_plan_only_preview_apply_and_idempotence_preserve_other_tables(db):
    plans = snapshot(db, 'member_plans')
    tables = ['membership_cards', 'membership_benefit_grants', 'users', 'orders', 'recharges', 'projects', 'price_book']
    protected = {table: snapshot(db, table) for table in tables}
    preview = reconcile_member_plans(db)
    db.commit()
    assert preview['changed'] == 2
    assert snapshot(db, 'member_plans') == plans
    reconcile_member_plans(db, apply=True, expected_hash=preview['preview_hash'])
    db.commit()
    after = snapshot(db, 'member_plans')
    assert after[2] == plans[2]
    assert (after[0]['price_cents'], after[1]['price_cents']) == (9900, 50000)
    assert '每周二按门店价消费任意主项，买一赠一' in json.loads(after[0]['benefits'])
    assert '另赠价值29.9元养生茶1盒' in json.loads(after[1]['benefits'])
    assert {table: snapshot(db, table) for table in tables} == protected
    assert reconcile_member_plans(db)['changed'] == 0
    reconcile_member_plans(db, apply=True, expected_hash=reconcile_member_plans(db)['preview_hash'])
    assert len(list(db.scalars(select(AuditLog)))) == 1


def test_plan_preview_drift_refuses_write(db):
    preview = reconcile_member_plans(db)
    db.get(MemberPlan, 1).price_cents = 10000
    db.commit()
    with pytest.raises(ValueError, match='preview_hash_mismatch'):
        reconcile_member_plans(db, apply=True, expected_hash=preview['preview_hash'])


def test_plan_apply_can_be_rolled_back_as_a_batch(db):
    before = snapshot(db, 'member_plans')
    reconcile_member_plans(db, apply=True, expected_hash=reconcile_member_plans(db)['preview_hash'])
    db.rollback()
    assert snapshot(db, 'member_plans') == before


def test_unrelated_monthly_drift_invalidates_preview_without_changing_it(db):
    preview = reconcile_member_plans(db)
    db.get(MemberPlan, 3).benefits = ['changed elsewhere']
    db.commit()
    with pytest.raises(ValueError, match='preview_hash_mismatch'):
        reconcile_member_plans(db, apply=True, expected_hash=preview['preview_hash'])


def test_cli_verifies_actual_backup_hash_before_database_access(tmp_path):
    backup = tmp_path / 'backup.dump'
    backup.write_bytes(b'synthetic-backup')
    result = subprocess.run([sys.executable, '-m', 'scripts.reconcile_member_plans_20261008',
                             '--apply', '--expected-hash', 'x', '--backup-reference', str(backup),
                             '--backup-sha256', '0' * 64], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'backup SHA256 mismatch' in result.stderr
