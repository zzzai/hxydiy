"""Preview or atomically provision an explicitly approved private staff batch.

Run with --input /private/batch.json; --apply requires --expect-preview-sha256.
Never include private inputs or credentials in source control.
"""

import argparse
import json
import re
import secrets
import stat
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.admin import hash_password
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, Staff, Store, Technician
from app.models.staff_access import StaffScopeAssignment
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_staff import WecomProvider, WecomProviderError, canonical_userid, local_binding
from scripts.bind_wecom_identity import BindingRefused, _sha


def _normalize(body):
    if (not isinstance(body, dict) or set(body) != {'corp_id', 'store_id', 'members'}
        or not settings.wecom_corp_id or body['corp_id'] != settings.wecom_corp_id
        or type(body['store_id']) is not int or body['store_id'] <= 0
        or not isinstance(body['members'], list) or not 1 <= len(body['members']) <= 3):
        raise BindingRefused('INVALID_INPUT')
    members = []
    for item in body['members']:
        if not isinstance(item, dict) or not isinstance(item.get('role'), str) or item['role'] not in {'manager', 'technician'}:
            raise BindingRefused('INVALID_INPUT')
        required = {'label', 'userid', 'username', 'name', 'role'}
        if item['role'] == 'technician':
            required |= {'phone', 'code'}
            if 'expected_wecom_name' in item:
                required.add('expected_wecom_name')
        if set(item) != required or any(not isinstance(item[key], str) for key in required):
            raise BindingRefused('INVALID_INPUT')
        name_keys = ('username', 'name') + (('expected_wecom_name',) if 'expected_wecom_name' in item else ())
        if (not re.fullmatch(r'(manager|technician)_[1-3]', item['label'])
            or not item['label'].startswith(item['role'] + '_')
            or any(not 1 <= len(item[key]) <= 32 or item[key] != item[key].strip()
                or any(ord(char) < 32 for char in item[key]) for key in name_keys)):
            raise BindingRefused('INVALID_INPUT')
        if item['role'] == 'technician' and (not re.fullmatch(r'1[0-9]{10}', item['phone'])
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', item['code'])):
            raise BindingRefused('INVALID_INPUT')
        members.append({**item, 'userid': canonical_userid(item['userid'])})
    for key in ('label', 'userid', 'username', 'name', 'phone', 'code'):
        values = [item[key] for item in members if key in item]
        if len(values) != len(set(values)):
            raise BindingRefused('DUPLICATE_INPUT')
    return {**body, 'members': members}


def _inspect(db, body, provider, lock=False):
    body = _normalize(body)
    request_sha = _sha(body)

    def rows(query):
        return list(db.scalars(query.with_for_update() if lock else query))

    stores = rows(select(Store).where(Store.id == body['store_id']))
    if len(stores) != 1:
        raise BindingRefused('STORE_NOT_FOUND')
    # The store lock serializes this tool's same-store batches, including new rows.
    plans, approvals = [], []
    for item in body['members']:
        provider.verify_member(item['userid'], expected_name=item.get('expected_wecom_name', item['name']))
        identities = rows(select(StaffExternalIdentity).where(StaffExternalIdentity.provider == 'wecom',
            StaffExternalIdentity.corp_id == body['corp_id'], StaffExternalIdentity.userid == item['userid']))
        staff_matches = rows(select(Staff).where(or_(Staff.username == item['username'], Staff.name == item['name'])))
        tech_conditions = [Technician.name == item['name']]
        if item['role'] == 'technician':
            tech_conditions += [Technician.phone == item['phone'], Technician.code == item['code']]
        tech_matches = rows(select(Technician).where(or_(*tech_conditions)))
        staff, tech, identity = None, None, None
        if identities:
            identity = identities[0]
            try:
                staff = local_binding(db, identity)
            except HTTPException:
                raise BindingRefused('IDENTITY_CONFLICT') from None
            if (staff_matches != [staff] or staff.username != item['username'] or staff.name != item['name']
                or staff.role != item['role'] or staff.store_id != body['store_id']
                or staff.temporary_expires_at is not None):
                raise BindingRefused('ACCOUNT_CONFLICT')
            if item['role'] == 'technician':
                tech = db.get(Technician, staff.technician_id)
                if (tech_matches != [tech] or tech.code != item['code'] or tech.name != item['name']
                    or tech.phone != item['phone'] or rows(select(StaffScopeAssignment).where(StaffScopeAssignment.staff_id == staff.id))):
                    raise BindingRefused('ACCOUNT_CONFLICT')
            elif tech_matches:
                raise BindingRefused('ACCOUNT_CONFLICT')
            audits = rows(select(AuditLog).where(AuditLog.action == 'wecom_staff.provision',
                AuditLog.entity_type == 'staff_external_identity', AuditLog.entity_id == str(identity.id)))
            if len(audits) != 1 or audits[0].detail.get('request_sha256') != request_sha:
                raise BindingRefused('ACCOUNT_CONFLICT')
            approvals.append(audits[0].detail.get('preview_sha256'))
        elif staff_matches or tech_matches:
            raise BindingRefused('ACCOUNT_CONFLICT')
        plans.append({'label': item['label'], 'role': item['role'], 'action': 'unchanged' if identity else 'create',
            'staff_id': staff.id if staff else None, 'technician_id': tech.id if tech else None,
            'identity_id': identity.id if identity else None})
    if approvals and len(approvals) != len(plans):
        raise BindingRefused('PARTIAL_BATCH_CONFLICT')
    plan = {'action': 'unchanged' if approvals else 'create_batch', 'request_sha256': request_sha,
        'store_id': body['store_id'], 'members': plans}
    plan['preview_sha256'] = _sha(plan)
    return plan, body, approvals


def prepare_provision(db, body, provider):
    return _inspect(db, body, provider)[0]


def apply_provision(db, body, expected, provider):
    plan, body, approvals = _inspect(db, body, provider, lock=True)
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise BindingRefused('PREVIEW_CHANGED')
    if plan['action'] == 'unchanged':
        if expected != plan['preview_sha256'] and any(expected != value for value in approvals):
            raise BindingRefused('PREVIEW_CHANGED')
        return plan
    if expected != plan['preview_sha256']:
        raise BindingRefused('PREVIEW_CHANGED')
    results = []
    for item in body['members']:
        tech = None
        if item['role'] == 'technician':
            tech = Technician(store_id=body['store_id'], name=item['name'], code=item['code'], phone=item['phone'], status='available')
            db.add(tech)
            db.flush()
        staff = Staff(username=item['username'], name=item['name'], role=item['role'], status='active',
            store_id=body['store_id'], technician_id=tech.id if tech else None,
            password_hash=hash_password(secrets.token_urlsafe(40)))
        db.add(staff)
        db.flush()
        if item['role'] == 'manager':
            db.add(StaffScopeAssignment(staff_id=staff.id, role='store_manager', scope_type='store',
                scope_id=body['store_id'], status='active'))
            db.flush()
        identity = StaffExternalIdentity(provider='wecom', corp_id=body['corp_id'], userid=item['userid'],
            staff_id=staff.id, technician_id=staff.technician_id, store_id=body['store_id'], status='active')
        local_binding(db, identity)
        db.add(identity)
        db.flush()
        result = {'label': item['label'], 'role': item['role'], 'staff_id': staff.id,
            'technician_id': staff.technician_id, 'identity_id': identity.id}
        results.append(result)
        db.add(AuditLog(actor_type='system', actor_id='wecom-provision-cli', store_id=body['store_id'],
            action='wecom_staff.provision', entity_type='staff_external_identity', entity_id=str(identity.id),
            detail={**result, 'request_sha256': plan['request_sha256'], 'preview_sha256': expected}))
    db.flush()
    return {'action': 'created', 'store_id': body['store_id'], 'request_sha256': plan['request_sha256'], 'members': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expect-preview-sha256')
    args = parser.parse_args()
    try:
        if (args.input.is_symlink() or not args.input.is_file()
            or stat.S_IMODE(args.input.stat().st_mode) & 0o077 or args.input.stat().st_size > 8192):
            raise BindingRefused('PRIVATE_INPUT_REQUIRED')
        body = json.loads(args.input.read_text())
        with SessionLocal.begin() as db:
            provider = WecomProvider()
            result = apply_provision(db, body, args.expect_preview_sha256, provider) if args.apply else prepare_provision(db, body, provider)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BindingRefused, WecomProviderError, SQLAlchemyError, ValueError, OSError):
        # Never expose SQL parameters, credentials, subjects or private input.
        print(json.dumps({'error': 'PROVISION_REFUSED', 'changed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
