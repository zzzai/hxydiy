from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import Depends
from jose import jwt
from sqlalchemy import select

import test_wecom_staff_auth as auth_harness
from app.api.admin import require_manager, require_technician
from app.core.config import settings
from app.models import Staff, StaffScopeAssignment, Store, Technician
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_notify import manager_userids
from app.services.wecom_staff import WecomProviderError


@pytest.fixture
def manager():
    harness = auth_harness.WecomStaffAuthTests()
    harness.setUp()
    try:
        with harness.sessions.begin() as db:
            staff = Staff(username='synthetic-manager', name='Synthetic manager', password_hash='unused',
                role='manager', store_id=harness.store_id, status='active')
            db.add(staff)
            db.flush()
            grant = StaffScopeAssignment(staff_id=staff.id, role='store_manager', scope_type='store',
                scope_id=harness.store_id, status='active')
            db.add(grant)
            db.flush()
            identity = StaffExternalIdentity(provider='wecom', corp_id='synthetic-corp', userid='user-1',
                staff_id=staff.id, technician_id=None, store_id=harness.store_id)
            db.add(identity)
            db.flush()
            harness.manager_id, harness.grant_id, harness.identity_id = staff.id, grant.id, identity.id

        @harness.app.get('/manager-only')
        def manager_only(staff=Depends(require_manager)):
            return {'staff_id': staff.id, 'store_id': staff.store_id, 'role': staff.role}

        @harness.app.get('/technician-only')
        def technician_only(staff=Depends(require_technician)):
            return {'staff_id': staff.id}

        yield harness
    finally:
        harness.tearDown()


def test_manager_exchange_uses_exact_store_scope_and_never_technician(manager):
    attempt, state = manager.authorize()
    assert manager.callback(state).status_code == 303
    response = manager.exchange(attempt)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['auth_method'] == 'wecom' and body['selector_token'] is None
    assert body['staff']['role'] == 'store_manager' and body['staff']['technician_id'] is None
    assert body['staff']['id'] == manager.manager_id and body['staff']['store_id'] == manager.store_id
    assert body['workspaces'] == [{'assignment_id': manager.grant_id, 'role': 'store_manager',
        'scope_type': 'store', 'scope_id': manager.store_id, 'scope_name': 'Synthetic store'}]
    payload = jwt.decode(body['token'], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload['token_type'] == 'staff_scope' and payload['role'] == 'store_manager'
    assert payload['assignment_id'] == manager.grant_id and payload['scope_id'] == manager.store_id
    assert payload['scope_type'] == 'store' and payload['external_identity_id'] == manager.identity_id
    headers = {'Authorization': 'Bearer ' + body['token']}
    assert manager.client.get('/manager-only', headers=headers).json() == {
        'staff_id': manager.manager_id, 'store_id': manager.store_id, 'role': 'manager'}
    assert manager.client.get('/technician-only', headers=headers).status_code == 403


def test_manager_with_technician_keeps_both_technician_and_manager_capabilities(manager):
    with manager.sessions.begin() as db:
        tech = Technician(store_id=manager.store_id, code='manager-tech', name='Manager tech', status='available')
        db.add(tech)
        db.flush()
        staff = db.get(Staff, manager.manager_id)
        staff.technician_id = tech.id
        db.get(StaffExternalIdentity, manager.identity_id).technician_id = tech.id
    manager.tech_id = tech.id
    attempt, state = manager.authorize()
    assert manager.callback(state).status_code == 303
    response = manager.exchange(attempt)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['staff']['role'] == 'store_manager'
    assert body['staff']['technician_id'] == manager.tech_id
    assert len(body['workspaces']) == 1
    headers = {'Authorization': 'Bearer ' + body['token']}
    assert manager.client.get('/manager-only', headers=headers).status_code == 200
    assert manager.client.get('/technician-only', headers=headers).status_code == 200


def test_manager_with_technician_still_receives_store_notifications(manager):
    with manager.sessions.begin() as db:
        tech = Technician(store_id=manager.store_id, code='notify-manager-tech', name='Notify manager', status='available')
        db.add(tech)
        db.flush()
        db.get(Staff, manager.manager_id).technician_id = tech.id
        db.get(StaffExternalIdentity, manager.identity_id).technician_id = tech.id
    with manager.sessions() as db:
        assert manager_userids(db, manager.store_id) == ['user-1']


@pytest.mark.parametrize('change', ['missing', 'other_store', 'multiple', 'brand', 'staff_role', 'staff_tech', 'disabled'])
def test_invalid_manager_binding_cannot_login(manager, change):
    with manager.sessions.begin() as db:
        grant = db.get(StaffScopeAssignment, manager.grant_id)
        staff = db.get(Staff, manager.manager_id)
        if change == 'missing':
            db.delete(grant)
        elif change == 'disabled':
            grant.status = 'disabled'
        elif change in {'other_store', 'multiple'}:
            other = Store(store_code='synthetic-other', name='Other', address='Synthetic')
            db.add(other)
            db.flush()
            if change == 'other_store':
                grant.scope_id = other.id
            else:
                db.add(StaffScopeAssignment(staff_id=staff.id, role='store_manager', scope_type='store', scope_id=other.id))
        elif change == 'brand':
            grant.role, grant.scope_type, grant.scope_id = 'brand_admin', 'brand', None
        elif change == 'staff_role':
            staff.role = 'admin'
        elif change == 'staff_tech':
            db.get(Staff, manager.staff_id).technician_id = None
            db.flush()
            staff.technician_id = manager.tech_id
    attempt, state = manager.authorize()
    manager.callback(state)
    assert manager.exchange(attempt).status_code == 401


@pytest.mark.parametrize('change', ['revoked', 'store_changed', 'role_changed', 'additional_grant'])
def test_manager_grant_changes_revoke_existing_wecom_token(manager, change):
    token = manager.login()
    with manager.sessions.begin() as db:
        grant = db.get(StaffScopeAssignment, manager.grant_id)
        if change == 'revoked':
            grant.status = 'disabled'
        elif change == 'role_changed':
            grant.role = 'store_staff'
        else:
            other = Store(store_code='changed-store', name='Changed', address='Synthetic')
            db.add(other)
            db.flush()
            if change == 'store_changed':
                grant.scope_id = other.id
            else:
                db.add(StaffScopeAssignment(staff_id=manager.manager_id, role='store_manager', scope_type='store', scope_id=other.id))
    assert manager.protected(token).status_code == 401


@pytest.mark.parametrize('field,value', [('role', 'manager'), ('token_type', 'staff'),
    ('assignment_id', 99999), ('scope_id', 99999), ('scope_type', 'brand')])
def test_manager_token_must_match_exact_grant(manager, field, value):
    payload = jwt.decode(manager.login(), settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    payload[field] = value
    forged = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert manager.protected(forged).status_code == 401


def test_manager_expired_official_proof_denied_without_refresh(manager):
    token = manager.login()
    old = datetime.now(timezone.utc) - timedelta(seconds=301)
    with manager.sessions.begin() as db:
        db.get(StaffExternalIdentity, manager.identity_id).provider_verified_at = old
    with patch.object(manager.provider, 'verify_member', side_effect=WecomProviderError()):
        assert manager.protected(token).status_code == 401
    with manager.sessions() as db:
        actual = db.get(StaffExternalIdentity, manager.identity_id).provider_verified_at
        assert actual.replace(tzinfo=timezone.utc) == old


def test_original_technician_wecom_contract_is_unchanged():
    harness = auth_harness.WecomStaffAuthTests()
    harness.setUp()
    try:
        harness.bind()
        token = harness.login()
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert payload['token_type'] == 'staff' and payload['role'] == 'technician'
        assert harness.protected(token).json() == {'staff_id': harness.staff_id, 'technician_id': harness.tech_id}
    finally:
        harness.tearDown()
