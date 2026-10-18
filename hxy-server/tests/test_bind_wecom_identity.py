import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import Base
from app.models import AuditLog, Staff, Store, Technician
from app.models.staff_external_identity import StaffExternalIdentity


def load_tool():
    path = Path(__file__).resolve().parents[1] / 'scripts/bind_wecom_identity.py'
    spec = importlib.util.spec_from_file_location('bind_wecom_identity', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Store(id=1, store_code='synthetic', name='Synthetic', address='Synthetic'))
        db.add(Staff(id=1, username='wecom-test-admin', name='Original', role='admin', status='active', password_hash='protected'))
        db.commit()
        yield db
    engine.dispose()


def request():
    return {'corp_id': 'synthetic-corp', 'userid': 'USER-1', 'store_id': 1,
            'create_test': {'username': 'wecom-test-user', 'code': 'wecom-test-tech', 'name': 'Synthetic test - do not assign'}}


def test_existing_manager_binding_requires_explicit_null_and_single_store_grant(database):
    from app.models.staff_access import StaffScopeAssignment
    tool = load_tool()
    database.add(Staff(id=2, username='manager-existing', name='Synthetic manager', password_hash='unused', role='manager', store_id=1))
    database.add(StaffScopeAssignment(staff_id=2, role='store_manager', scope_type='store', scope_id=1))
    database.commit()
    body = {'corp_id': 'synthetic-corp', 'userid': 'MANAGER-1', 'store_id': 1, 'staff_id': 2, 'technician_id': None}
    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'):
        preview = tool.prepare_binding(database, body)
        result = tool.apply_binding(database, body, preview['preview_sha256'])
        database.commit()
        assert result['technician_id'] is None and counts(database) == [2, 0, 1, 1]
        assert tool.apply_binding(database, body, preview['preview_sha256'])['action'] == 'unchanged'
        for change in ({'staff_id': 1}, {'technician_id': 999}, {'store_id': 999}):
            with pytest.raises(tool.BindingRefused):
                tool.prepare_binding(database, {**body, **change})


def counts(db):
    return [db.scalar(select(func.count()).select_from(model)) for model in (Staff, Technician, StaffExternalIdentity, AuditLog)]


def test_preview_apply_replay_protects_old_staff_and_never_returns_secret(database):
    tool = load_tool()
    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'):
        preview = tool.prepare_binding(database, request())
        assert preview.get('action') == 'create_test'
        assert counts(database) == [1, 0, 0, 0]
        assert 'user-1' not in str(preview).lower()
        result = tool.apply_binding(database, request(), preview['preview_sha256'])
        database.commit()
        assert result['action'] == 'created'
        assert counts(database) == [2, 1, 1, 1]
        staff = database.get(Staff, result['staff_id'])
        tech = database.get(Technician, result['technician_id'])
        assert (staff.role, staff.status, staff.store_id, staff.technician_id) == ('technician', 'active', 1, tech.id)
        assert tech.name == 'Synthetic test - do not assign'
        assert tech.status == 'available'
        assert staff.password_hash not in str(result)
        old = database.get(Staff, 1)
        assert (old.role, old.password_hash, old.name) == ('admin', 'protected', 'Original')
        replay = tool.apply_binding(database, request(), preview['preview_sha256'])
        database.commit()
        assert replay['action'] == 'unchanged'
        assert counts(database) == [2, 1, 1, 1]
        identity = database.scalar(select(StaffExternalIdentity))
        assert identity.userid == 'user-1'
        assert identity.provider_verified_at is None


def test_stale_preview_and_name_collisions_do_not_write(database):
    tool = load_tool()
    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'):
        with pytest.raises(tool.BindingRefused, match='PREVIEW_CHANGED'):
            tool.apply_binding(database, request(), '0' * 64)
        assert counts(database) == [1, 0, 0, 0]
        changed = request()
        changed['create_test']['username'] = 'wecom-test-admin'
        with pytest.raises(tool.BindingRefused, match='ACCOUNT_CONFLICT'):
            tool.prepare_binding(database, changed)
        assert counts(database) == [1, 0, 0, 0]


def test_existing_binding_requires_explicit_matching_technician_and_store(database):
    tool = load_tool()
    database.add(Technician(id=1, store_id=1, code='synthetic-tech', name='Synthetic', status='available'))
    database.add(Staff(id=2, username='synthetic-tech', password_hash='unused', role='technician', status='active', store_id=1, technician_id=1))
    database.commit()
    body = {'corp_id': 'synthetic-corp', 'userid': 'USER-1', 'store_id': 1, 'staff_id': 2, 'technician_id': 1}
    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'):
        for field, value in [('staff_id', 1), ('technician_id', 99), ('store_id', 99), ('corp_id', 'other-corp')]:
            with pytest.raises(tool.BindingRefused):
                tool.prepare_binding(database, {**body, field: value})
        preview = tool.prepare_binding(database, body)
        result = tool.apply_binding(database, body, preview['preview_sha256'])
        database.commit()
        assert result['action'] == 'created'
        assert counts(database) == [2, 1, 1, 1]
        with pytest.raises(tool.BindingRefused, match='ACCOUNT_CONFLICT'):
            tool.prepare_binding(database, {**body, 'userid': 'another-user'})
        identity = database.scalar(select(StaffExternalIdentity))
        identity.status = 'disabled'
        database.commit()
        with pytest.raises(tool.BindingRefused, match='IDENTITY_CONFLICT'):
            tool.prepare_binding(database, body)


@pytest.mark.skipif(os.name != 'posix', reason='Server CLI requires POSIX private-file permissions')
def test_cli_is_preview_by_default_and_provider_failure_cannot_write(database, tmp_path, capsys):
    tool = load_tool()
    private = tmp_path / 'input.json'
    private.write_text(json.dumps(request()))
    private.chmod(0o600)
    argv = ['bind_wecom_identity', '--input', str(private)]
    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'), patch.object(tool, 'SessionLocal', sessionmaker(bind=database.bind)), patch.object(tool.WecomProvider, 'verify_member'), patch('sys.argv', argv):
        assert tool.main() == 0
        preview = json.loads(capsys.readouterr().out)
        assert counts(database) == [1, 0, 0, 0]
        with patch('sys.argv', argv + ['--apply', '--expect-preview-sha256', preview['preview_sha256']]), patch.object(tool.WecomProvider, 'verify_member', side_effect=tool.WecomProviderError()):
            assert tool.main() == 1
        assert counts(database) == [1, 0, 0, 0]
        assert 'user-1' not in capsys.readouterr().out.lower()


@pytest.mark.skipif(os.name != 'posix', reason='Server CLI requires POSIX private-file permissions')
def test_cli_database_failure_does_not_expose_sql_parameters(database, tmp_path, capsys):
    tool = load_tool()
    private = tmp_path / 'input.json'
    private.write_text(json.dumps(request()))
    private.chmod(0o600)
    with patch('sys.argv', ['bind_wecom_identity', '--input', str(private)]), patch.object(tool.SessionLocal, 'begin', side_effect=SQLAlchemyError('sensitive-userid-in-query')):
        assert tool.main() == 1
    assert json.loads(capsys.readouterr().out) == {'error': 'BINDING_REFUSED', 'changed': False}


@pytest.mark.skipif(os.name != 'posix', reason='Server CLI requires POSIX private-file permissions')
def test_cli_failed_identity_insert_rolls_back_new_staff_and_technician(database, tmp_path, capsys):
    tool = load_tool()
    private = tmp_path / 'input.json'
    private.write_text(json.dumps(request()))
    private.chmod(0o600)

    def fail_identity_insert(mapper, connection, target):
        raise SQLAlchemyError('synthetic identity insert failure')

    with patch.object(settings, 'wecom_corp_id', 'synthetic-corp'):
        preview = tool.prepare_binding(database, request())
        event.listen(StaffExternalIdentity, 'before_insert', fail_identity_insert)
        try:
            with patch.object(tool, 'SessionLocal', sessionmaker(bind=database.bind)), patch.object(tool.WecomProvider, 'verify_member'), patch('sys.argv', ['bind_wecom_identity', '--input', str(private), '--apply', '--expect-preview-sha256', preview['preview_sha256']]):
                assert tool.main() == 1
        finally:
            event.remove(StaffExternalIdentity, 'before_insert', fail_identity_insert)
    assert counts(database) == [1, 0, 0, 0]
    assert json.loads(capsys.readouterr().out) == {'error': 'BINDING_REFUSED', 'changed': False}
