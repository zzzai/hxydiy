from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import AuditLog, Room, Store, SelectionSession, PositionOccupancy
from app.models.service_position_qr import ServicePositionQr
from app.api.occupancies import _managed_position_qr_token, _managed_position_short_code, resolve_position_qr_token
from scripts.rebind_printed_sofas import rebind_printed_sofas


@pytest.fixture
def db():
    url = os.environ.get('QR_BINDING_TEST_DATABASE_URL', 'sqlite://')
    control = None
    if url != 'sqlite://':
        if make_url(url).database != 'qr_binding_test':
            raise ValueError('isolated_test_database_required')
        schema = 'qr_test_' + uuid.uuid4().hex
        control = create_engine(url, isolation_level='AUTOCOMMIT')
        with control.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
        engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    else:
        engine = create_engine(url)
    Base.metadata.create_all(engine)
    if engine.dialect.name == 'sqlite':
        with engine.connect() as connection:
            connection.execute(text('PRAGMA foreign_keys=ON'))
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        db.add(Store(id=1, name='Synthetic', store_code='synthetic', address='Synthetic'))
        db.flush()
        for i, n in enumerate([5, 3, 2, 1, 9, 8, 7, 6], 1):
            db.add(Room(id=i, store_id=1, code=f'sofa-{i:02}', name=f'{n}号沙发',
                        customer_label=f'{n}号沙发', room_type='sofa', status='available',
                        map_x=0.08 if i <= 4 else 0.7,
                        map_y=[0.14, 0.34, 0.54, 0.74][(i - 1) % 4]))
        db.add(Room(id=9, store_id=1, code='room-01', name='Parking', room_type='room',
                    is_service_position=False, is_space_container=True))
        db.flush()
        for i in range(1, 9):
            db.add(ServicePositionQr(id=i + 2, public_id=f'00000000-0000-0000-0000-{i:012}',
                                     short_code_hash=str(i) * 64, store_id=1, room_id=i))
        db.commit()
        yield db
    engine.dispose()
    if control:
        with control.connect() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()


def rows(db, table):
    return [dict(r) for r in db.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings()]


def test_preview_and_atomic_swaps_preserve_every_other_field(db):
    before = rows(db, 'service_position_qrs')
    rooms = rows(db, 'rooms')
    credentials = [(_managed_position_qr_token(db.get(ServicePositionQr, i + 2), ''),
                    _managed_position_short_code(db.get(ServicePositionQr, i + 2))) for i in range(1, 9)]
    preview = rebind_printed_sofas(db)
    db.commit()
    assert rows(db, 'service_position_qrs') == before
    assert preview['changed'] == 8
    result = rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])
    db.commit()
    assert result['changed'] == 8
    assert rows(db, 'rooms') == rooms
    after = rows(db, 'service_position_qrs')
    assert [r['room_id'] for r in after] == [4, 3, 2, 1, 8, 7, 6, 5]
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k != 'room_id'} == {k: v for k, v in new.items() if k != 'room_id'}
    for i, ((token, short), room_id) in enumerate(zip(credentials, [4, 3, 2, 1, 8, 7, 6, 5]), 3):
        qr, room = resolve_position_qr_token(db, token)
        assert (qr.id, room.id) == (i, room_id)
        assert _managed_position_short_code(qr) == short
    db.rollback()
    assert rebind_printed_sofas(db, apply=True, expected_hash=rebind_printed_sofas(db)['preview_hash'])['changed'] == 0
    assert len(list(db.scalars(select(AuditLog)))) == 1


def test_rollback_does_not_publish_parking_or_partial_bindings(db):
    before = rows(db, 'service_position_qrs')
    rebind_printed_sofas(db, apply=True, expected_hash=rebind_printed_sofas(db)['preview_hash'])
    db.rollback()
    assert rows(db, 'service_position_qrs') == before
    assert not list(db.scalars(select(AuditLog)))


@pytest.mark.parametrize('expired', [False, True])
def test_live_selection_blocks_but_expired_history_is_preserved(db, expired):
    db.add(SelectionSession(id='test-session', store_id=1, access_token_hash='x' * 64,
                            status='submitted', expires_at=datetime.now(timezone.utc) + timedelta(days=-1 if expired else 1)))
    db.flush()
    db.add(PositionOccupancy(id=1, store_id=1, room_id=1, selection_session_id='test-session', status='released'))
    db.commit()
    history = rows(db, 'selection_sessions'), rows(db, 'position_occupancies')
    preview = rebind_printed_sofas(db)
    if expired:
        rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])
        assert (rows(db, 'selection_sessions'), rows(db, 'position_occupancies')) == history
    else:
        with pytest.raises(ValueError, match='active_business'):
            rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])


def test_changed_qr_identity_invalidates_approved_preview(db):
    preview = rebind_printed_sofas(db)
    db.get(ServicePositionQr, 3).public_id = 'new-identity'
    db.commit()
    with pytest.raises(ValueError, match='preview_drift'):
        rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])


def test_entry_rechecks_binding_after_room_lock_before_browser_writes(db, monkeypatch):
    from fastapi import HTTPException
    from app.api import occupancies
    from app.schemas.occupancy import EntrySessionIn

    token = _managed_position_qr_token(db.get(ServicePositionQr, 3), '')

    def concurrent_swap(session, store_id):
        # Simulate a committed binding change after initial token verification.
        for qr_id, room_id in [(3, 9), (6, 1), (3, 4)]:
            session.execute(text('UPDATE service_position_qrs SET room_id=:room WHERE id=:qr'),
                            {'room': room_id, 'qr': qr_id})

    def forbidden_browser_write(*args):
        raise AssertionError('stale QR reached browser identity creation')

    monkeypatch.setattr(occupancies, 'expire_stale_holds', concurrent_swap)
    monkeypatch.setattr(occupancies, '_browser_customer', forbidden_browser_write)
    with pytest.raises(HTTPException) as error:
        occupancies._create_entry(db, EntrySessionIn(store_id=1, position_code='sofa-01',
                                 source='personal_qr', entry_token=token), None)
    assert error.value.status_code == 403


@pytest.mark.parametrize('field,value', [('status', 'disabled'), ('source', 'room_qr'),
                                        ('short_code_hash', None), ('room_id', 9)])
def test_unexpected_qr_state_or_partial_binding_is_rejected(db, field, value):
    setattr(db.get(ServicePositionQr, 3), field, value)
    db.commit()
    before = rows(db, 'service_position_qrs')
    with pytest.raises(ValueError):
        rebind_printed_sofas(db, apply=True, expected_hash='invalid')
    db.rollback()
    assert rows(db, 'service_position_qrs') == before


def test_new_expired_record_still_invalidates_preview(db):
    preview = rebind_printed_sofas(db)
    db.add(SelectionSession(id='new', store_id=1, access_token_hash='x' * 64,
                            status='expired', expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db.flush()
    db.add(PositionOccupancy(id=1, store_id=1, room_id=1, selection_session_id='new', status='released'))
    db.commit()
    with pytest.raises(ValueError, match='preview_drift'):
        rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])


def test_active_occupancy_refuses_swap(db):
    db.add(SelectionSession(id='occupied', store_id=1, access_token_hash='x' * 64, status='confirmed'))
    db.flush()
    db.add(PositionOccupancy(id=1, store_id=1, room_id=1, active_room_id=1,
                             selection_session_id='occupied', active_session_id='occupied', status='in_service'))
    db.commit()
    preview = rebind_printed_sofas(db)
    assert preview['blockers']['active_occupancies'] == 1
    with pytest.raises(ValueError, match='active_business'):
        rebind_printed_sofas(db, apply=True, expected_hash=preview['preview_hash'])


def test_missing_parking_room_refuses_all_writes(db):
    db.delete(db.get(Room, 9))
    db.commit()
    before = rows(db, 'service_position_qrs')
    with pytest.raises(ValueError, match='parking_unavailable'):
        rebind_printed_sofas(db, apply=True, expected_hash=rebind_printed_sofas(db)['preview_hash'])
    assert rows(db, 'service_position_qrs') == before


def test_postgres_apply_blocks_concurrent_entry_row_locks(db):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('isolated PostgreSQL required')
    from sqlalchemy.exc import OperationalError

    rebind_printed_sofas(db, apply=True, expected_hash=rebind_printed_sofas(db)['preview_hash'])
    with Session(db.bind) as concurrent:
        concurrent.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(OperationalError) as error:
            concurrent.scalar(select(Room).where(Room.id == 1).with_for_update())
        assert error.value.orig.sqlstate == '55P03'
        concurrent.rollback()
    db.rollback()
    assert db.get(ServicePositionQr, 3).room_id == 1


def test_cli_rejects_wrong_backup_hash_before_database_access(tmp_path):
    backup = tmp_path / 'backup.dump'
    backup.write_bytes(b'synthetic-backup')
    result = subprocess.run([sys.executable, '-m', 'scripts.rebind_printed_sofas',
                             '--apply', '--expected-hash', 'x', '--backup-reference', str(backup),
                             '--backup-sha256', '0' * 64], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'backup SHA256 mismatch' in result.stderr
