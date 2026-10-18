import importlib.util
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import SQLAlchemyError

import test_wecom_staff_auth as auth_harness
from app.models import AuditLog, Staff, Technician
from app.models.staff_access import StaffScopeAssignment
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_staff import WecomProvider, WecomProviderError


def load_tool():
    path = Path(__file__).resolve().parents[1] / 'scripts/provision_wecom_staff.py'
    spec = importlib.util.spec_from_file_location('provision_wecom_staff', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness():
    value = auth_harness.WecomStaffAuthTests()
    value.setUp()
    try:
        yield value
    finally:
        value.tearDown()


def request(store_id):
    members = [{'label': 'manager_1', 'userid': 'MANAGER-NEW', 'username': 'synthetic-manager',
        'name': 'Synthetic manager', 'role': 'manager'}]
    for index in (1, 2):
        members.append({'label': 'technician_' + str(index), 'userid': 'TECH-NEW-' + str(index),
            'username': 'synthetic-tech-' + str(index), 'name': 'Synthetic technician ' + str(index),
            'role': 'technician', 'phone': '1300000000' + str(index), 'code': 'synthetic-new-' + str(index)})
    return {'corp_id': 'synthetic-corp', 'store_id': store_id, 'members': members}


def counts(db):
    return [db.scalar(select(func.count()).select_from(model)) for model in
        (Staff, Technician, StaffScopeAssignment, StaffExternalIdentity, AuditLog)]


def test_preview_apply_replay_and_old_records_unchanged(harness):
    tool, provider = load_tool(), Mock()
    body = request(harness.store_id)
    with harness.sessions() as db:
        before = counts(db)
        preview = tool.prepare_provision(db, body, provider)
        assert preview.get('action') == 'create_batch'
        assert counts(db) == before
        assert len(preview['members']) == 3
        assert all(member['action'] == 'create' for member in preview['members'])
        result = tool.apply_provision(db, body, preview['preview_sha256'], provider)
        db.commit()
        assert result['action'] == 'created'
        assert counts(db) == [a + b for a, b in zip(before, [3, 2, 1, 3, 3])]
        for item in result['members']:
            staff = db.get(Staff, item['staff_id'])
            identity = db.get(StaffExternalIdentity, item['identity_id'])
            assert staff.store_id == identity.store_id == harness.store_id
            assert staff.status == identity.status == 'active'
            assert identity.provider_verified_at is None
            assert staff.password_hash not in str(result) and len(staff.password_hash) > 30
            if item['role'] == 'manager':
                assert staff.role == 'manager' and staff.technician_id is identity.technician_id is None
                grant = db.scalar(select(StaffScopeAssignment).where(StaffScopeAssignment.staff_id == staff.id))
                assert (grant.role, grant.scope_type, grant.scope_id) == ('store_manager', 'store', harness.store_id)
            else:
                assert staff.role == 'technician' and staff.technician_id == identity.technician_id
        old = db.get(Staff, harness.staff_id)
        assert (old.username, old.password_hash, old.role, old.technician_id) == ('wecom-test', 'unused', 'technician', harness.tech_id)
        after = counts(db)
        replay = tool.apply_provision(db, body, preview['preview_sha256'], provider)
        db.commit()
        assert replay['action'] == 'unchanged' and counts(db) == after
        assert all(secret not in json.dumps([preview, result, replay]) for secret in
            ['MANAGER-NEW', 'manager-new', 'Synthetic manager', '13000000001'])
        provider.verify_member.assert_any_call('manager-new', expected_name='Synthetic manager')


@pytest.mark.parametrize('kind', ['username', 'name', 'phone', 'code', 'duplicate_subject', 'role', 'extra_field'])
def test_conflicts_or_invalid_inputs_refused_without_changes(harness, kind):
    tool, body = load_tool(), request(harness.store_id)
    with harness.sessions() as db:
        before = counts(db)
        if kind == 'username':
            body['members'][0]['username'] = 'wecom-test'
        elif kind == 'name':
            body['members'][0]['name'] = 'Synthetic'
        elif kind in {'phone', 'code'}:
            if kind == 'phone':
                db.get(Technician, harness.tech_id).phone = '13000000001'
                db.commit()
            else:
                body['members'][1]['code'] = 'wecom-test-tech'
        elif kind == 'duplicate_subject':
            body['members'][1]['userid'] = body['members'][0]['userid'].lower()
        elif kind == 'role':
            body['members'][0]['role'] = 'admin'
        else:
            body['members'][0]['assignment_id'] = 1
        with pytest.raises(tool.BindingRefused):
            tool.prepare_provision(db, body, Mock())
        assert counts(db) == before


def test_stale_preview_provider_failure_and_disabled_replay_refuse(harness):
    tool, body = load_tool(), request(harness.store_id)
    with harness.sessions() as db:
        before = counts(db)
        preview = tool.prepare_provision(db, body, Mock())
        with pytest.raises(tool.BindingRefused, match='PREVIEW_CHANGED'):
            tool.apply_provision(db, body, '0' * 64, Mock())
        failing = Mock()
        failing.verify_member.side_effect = [None, WecomProviderError()]
        with pytest.raises(WecomProviderError):
            tool.apply_provision(db, body, preview['preview_sha256'], failing)
        assert counts(db) == before
        result = tool.apply_provision(db, body, preview['preview_sha256'], Mock())
        db.commit()
        db.get(Staff, result['members'][0]['staff_id']).status = 'disabled'
        db.commit()
        with pytest.raises(tool.BindingRefused):
            tool.apply_provision(db, body, preview['preview_sha256'], Mock())
        assert db.get(Staff, result['members'][0]['staff_id']).status == 'disabled'


@pytest.mark.skipif(os.name != 'posix', reason='Private server input permissions')
def test_cli_default_preview_and_mid_batch_failure_roll_back(harness, tmp_path, capsys):
    tool = load_tool()
    private = tmp_path / 'private.json'
    private.write_text(json.dumps(request(harness.store_id)))
    private.chmod(0o600)
    argv = ['provision_wecom_staff', '--input', str(private)]
    with patch.object(tool, 'SessionLocal', harness.sessions), patch.object(tool.WecomProvider, 'verify_member'), patch('sys.argv', argv):
        assert tool.main() == 0
        preview = json.loads(capsys.readouterr().out)
        with harness.sessions() as db:
            before = counts(db)

        def fail_second(mapper, connection, identity):
            if identity.userid == 'tech-new-1':
                raise SQLAlchemyError('private subject must not leak')

        event.listen(StaffExternalIdentity, 'before_insert', fail_second)
        try:
            with patch('sys.argv', argv + ['--apply', '--expect-preview-sha256', preview['preview_sha256']]):
                assert tool.main() == 1
        finally:
            event.remove(StaffExternalIdentity, 'before_insert', fail_second)
        assert json.loads(capsys.readouterr().out) == {'error': 'PROVISION_REFUSED', 'changed': False}
        with harness.sessions() as db:
            assert counts(db) == before
        private.chmod(0o644)
        assert tool.main() == 1
        assert json.loads(capsys.readouterr().out) == {'error': 'PROVISION_REFUSED', 'changed': False}


@pytest.mark.parametrize('matches', [False, True])
def test_provider_requires_exact_approved_name(harness, matches):
    provider = WecomProvider()
    member = {'userid': 'canonical-user', 'status': 1, 'name': 'Approved person' if matches else 'Different person'}
    with patch.object(provider, '_access_token', return_value='synthetic'), patch.object(provider, '_request', side_effect=[member, {'agentid': '1000002', 'close': 0}]):
        if matches:
            provider.verify_member('canonical-user', expected_name='Approved person')
        else:
            with pytest.raises(WecomProviderError):
                provider.verify_member('canonical-user', expected_name='Approved person')


@pytest.mark.skipif(not os.environ.get('WECOM_TEST_DATABASE_URL'), reason='PostgreSQL row-lock concurrency')
def test_concurrent_same_batch_serializes_to_one_creation(harness):
    tool, body = load_tool(), request(harness.store_id)
    with harness.sessions() as db:
        before = counts(db)
        preview = tool.prepare_provision(db, body, Mock())
    barrier = threading.Barrier(2)

    def submit():
        with harness.sessions.begin() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            return tool.apply_provision(db, body, preview['preview_sha256'], Mock())['action']

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == ['created', 'unchanged']
    with harness.sessions() as db:
        assert counts(db) == [a + b for a, b in zip(before, [3, 2, 1, 3, 3])]
