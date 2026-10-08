"""Synchronize only the two confirmed membership plans; preview by default."""

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import AuditLog, MemberPlan


PLAN_COPY = {
    'annual': ('年度会员权益卡', 9900, [
        '一年有效，消费享会员价',
        '每周二按门店价消费任意主项，买一赠一',
        '开卡赠门店价不高于99元项目1次',
        '赠送及周二组合由门店确认，不自动抵扣',
    ]),
    'stored': ('储值权益卡', 50000, [
        '余额耗尽失效，有效期间消费享会员价',
        '每周二按门店价消费任意主项，买一赠一',
        '开卡赠门店价不高于99元项目1次',
        '另赠价值29.9元养生茶1盒',
        '赠送及周二组合由门店确认，不自动抵扣',
    ]),
}


def reconcile_member_plans(db, *, apply=False, expected_hash=None):
    if apply and db.bind.dialect.name == 'postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        db.execute(text('LOCK TABLE member_plans IN EXCLUSIVE MODE'))
    query = select(MemberPlan).order_by(MemberPlan.id)
    plans = list(db.scalars(query.with_for_update() if apply else query))
    targets = {plan.code: plan for plan in plans if plan.code in PLAN_COPY}
    if len(targets) != 2 or any(plan.status != 'published' for plan in targets.values()):
        raise ValueError('published_membership_plan_missing')
    baseline = [{'id': plan.id, 'code': plan.code, 'name': plan.name,
                 'price_cents': plan.price_cents, 'benefits': plan.benefits,
                 'status': plan.status} for plan in plans]
    changes = []
    for code, (name, price, benefits) in PLAN_COPY.items():
        plan = targets[code]
        delta = {key: {'before': getattr(plan, key), 'after': value}
                 for key, value in dict(name=name, price_cents=price, benefits=benefits).items()
                 if getattr(plan, key) != value}
        if delta:
            changes.append({'id': plan.id, 'code': code, 'fields': delta})
    preview_hash = hashlib.sha256(json.dumps({'baseline': baseline, 'changes': changes},
                                 ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    report = {'changed': len(changes), 'changes': changes, 'preview_hash': preview_hash}
    if apply:
        if expected_hash != preview_hash:
            raise ValueError('preview_hash_mismatch')
        for change in changes:
            for key, delta in change['fields'].items():
                setattr(targets[change['code']], key, delta['after'])
        if changes:
            db.add(AuditLog(actor_type='system', actor_id='MEMBER-BENEFITS-20261008',
                            action='membership_plan_copy_reconciled', entity_type='member_plan',
                            entity_id='annual,stored', detail=report))
        db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-hash')
    parser.add_argument('--backup-reference', type=Path)
    parser.add_argument('--backup-sha256')
    args = parser.parse_args()
    if args.apply:
        backup = args.backup_reference
        if not args.expected_hash or not backup or backup.is_symlink() or not backup.is_file() or backup.stat().st_size == 0:
            parser.error('apply requires exact preview hash and a nonempty actual backup')
        with backup.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if not args.backup_sha256 or digest != args.backup_sha256:
            parser.error('backup SHA256 mismatch')
    with SessionLocal() as db:
        try:
            if not args.apply and db.bind.dialect.name == 'postgresql':
                db.execute(text('SET TRANSACTION READ ONLY'))
            report = reconcile_member_plans(db, apply=args.apply, expected_hash=args.expected_hash)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
