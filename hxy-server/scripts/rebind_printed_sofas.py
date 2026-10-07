"""Correct the eight original printed short QR bindings; preview by default."""

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import AuditLog, Room
from app.models.service_position_qr import ServicePositionQr
from scripts.relabel_sofas import relabel_sofas

TARGETS = {3: 4, 4: 3, 5: 2, 6: 1, 7: 8, 8: 7, 9: 6, 10: 5}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     ensure_ascii=False).encode()).hexdigest()


def blockers(db):
    # Expired or terminal historical sessions are not current room occupancy.
    queries = {
        'active_occupancies': "SELECT count(*) FROM position_occupancies WHERE active_room_id BETWEEN 1 AND 8",
        'live_selections': "SELECT count(DISTINCT s.id) FROM selection_sessions s JOIN position_occupancies p ON p.selection_session_id=s.id WHERE p.room_id BETWEEN 1 AND 8 AND s.status IN ('draft','submitted') AND (s.expires_at IS NULL OR s.expires_at>CURRENT_TIMESTAMP)",
        'service_assignments': "SELECT count(*) FROM service_assignments WHERE room_id BETWEEN 1 AND 8 AND status NOT IN ('completed','cancelled','reassigned')",
        'service_lines': "SELECT count(DISTINCT l.id) FROM service_lines l JOIN selection_sessions s ON s.id=l.selection_session_id JOIN position_occupancies p ON p.selection_session_id=s.id WHERE p.room_id BETWEEN 1 AND 8 AND s.status NOT IN ('cancelled','expired') AND l.state IN ('pending','in_service')",
        'change_requests': "SELECT count(DISTINCT r.id) FROM selection_change_requests r JOIN selection_sessions s ON s.id=r.selection_session_id JOIN position_occupancies p ON p.selection_session_id=s.id WHERE p.room_id BETWEEN 1 AND 8 AND s.status NOT IN ('cancelled','expired') AND r.state='awaiting_staff_confirmation'",
    }
    return {key: db.scalar(text(query)) for key, query in queries.items()}


def history_fingerprint(db):
    queries = [
        'SELECT id,room_id,active_room_id,active_session_id,selection_session_id,status,version,updated_at FROM position_occupancies WHERE room_id BETWEEN 1 AND 8 ORDER BY id',
        'SELECT DISTINCT s.id,s.status,s.expires_at,s.updated_at,s.fulfillment_order_id FROM selection_sessions s JOIN position_occupancies p ON p.selection_session_id=s.id WHERE p.room_id BETWEEN 1 AND 8 ORDER BY s.id',
        'SELECT id,room_id,status,finished_at FROM service_assignments WHERE room_id BETWEEN 1 AND 8 ORDER BY id',
        'SELECT DISTINCT l.id,l.state,l.selection_session_id FROM service_lines l JOIN position_occupancies p ON p.selection_session_id=l.selection_session_id WHERE p.room_id BETWEEN 1 AND 8 ORDER BY l.id',
        'SELECT DISTINCT r.id,r.state,r.selection_session_id FROM selection_change_requests r JOIN position_occupancies p ON p.selection_session_id=r.selection_session_id WHERE p.room_id BETWEEN 1 AND 8 ORDER BY r.id',
    ]
    return fingerprint([[dict(r) for r in db.execute(text(q)).mappings()] for q in queries])


def rebind_printed_sofas(db, *, apply=False, expected_hash=None):
    if apply and db.bind.dialect.name == 'postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        # Block writers and SELECT FOR UPDATE until the atomic correction ends.
        db.execute(text('LOCK TABLE rooms, service_position_qrs, position_occupancies, '
                        'selection_sessions, service_assignments, service_lines, '
                        'selection_change_requests IN EXCLUSIVE MODE'))
    label_check = relabel_sofas(db)
    if label_check['changed']:
        raise ValueError('seat_labels_not_current')
    rooms = list(db.scalars(select(Room).where(Room.id.between(1, 8)).order_by(Room.id)))
    if any(room.status != 'available' or room.operational_status != 'active' for room in rooms):
        raise ValueError('room_not_available')
    qr_rows = [dict(r) for r in db.execute(text(
        'SELECT * FROM service_position_qrs WHERE id BETWEEN 3 AND 10 ORDER BY id')).mappings()]
    if len(qr_rows) != 8 or any(q['store_id'] != 1 or q['status'] != 'active'
                              or q['source'] != 'personal_qr' or not q['short_code_hash'] for q in qr_rows):
        raise ValueError('qr_identity_drift')
    actual = {q['id']: q['room_id'] for q in qr_rows}
    original = {i: i - 2 for i in TARGETS}
    if actual not in (original, TARGETS):
        raise ValueError('qr_binding_drift')
    if db.scalar(text("SELECT count(*) FROM service_position_qrs WHERE room_id BETWEEN 1 AND 8 AND status='active' AND id NOT BETWEEN 3 AND 10")):
        raise ValueError('unexpected_active_qr')
    room_rows = [dict(r) for r in db.execute(text('SELECT * FROM rooms WHERE id BETWEEN 1 AND 8 ORDER BY id')).mappings()]
    # No tokens or personal data are included in the report.
    protected = fingerprint([{k: v for k, v in q.items() if k not in ('room_id', 'last_accessed_at', 'updated_at')} for q in qr_rows])
    current_blockers = blockers(db)
    plan = [{'qr_id': i, 'before_room_id': actual[i], 'after_room_id': TARGETS[i],
             'after_label': rooms[TARGETS[i] - 1].customer_label} for i in TARGETS]
    report = {'changed': sum(actual[i] != TARGETS[i] for i in TARGETS), 'mapping': plan,
              'blockers': current_blockers, 'qr_protected_hash': protected,
              'rooms_hash': fingerprint(room_rows), 'history_hash': history_fingerprint(db)}
    report['preview_hash'] = fingerprint(report)
    if not apply:
        return report
    if expected_hash != report['preview_hash']:
        raise ValueError('preview_drift')
    if any(current_blockers.values()):
        raise ValueError('active_business')
    if not report['changed']:
        return report
    # A real unbound container satisfies the non-null FK while swapping pairs.
    parking = db.scalar(select(Room).where(Room.store_id == 1, Room.id > 8,
                         Room.is_space_container.is_(True), Room.status == 'available',
                         Room.id.not_in(select(ServicePositionQr.room_id).where(ServicePositionQr.status == 'active')))
                        .order_by(Room.id).with_for_update())
    if not parking or db.scalar(text('SELECT count(*) FROM position_occupancies WHERE active_room_id=:room'), {'room': parking.id}):
        raise ValueError('parking_unavailable')
    if db.scalar(text("SELECT count(*) FROM service_assignments WHERE room_id=:room AND status NOT IN ('completed','cancelled','reassigned')"), {'room': parking.id}):
        raise ValueError('parking_unavailable')
    for first, second in [(3, 6), (4, 5), (7, 10), (8, 9)]:
        for qr_id, room_id in [(first, parking.id), (second, original[first]), (first, original[second])]:
            db.execute(text('UPDATE service_position_qrs SET room_id=:room WHERE id=:qr'),
                       {'room': room_id, 'qr': qr_id})
    after = [dict(r) for r in db.execute(text('SELECT * FROM service_position_qrs WHERE id BETWEEN 3 AND 10 ORDER BY id')).mappings()]
    for old, new in zip(qr_rows, after):
        if new['room_id'] != TARGETS[new['id']] or any(old[k] != new[k] for k in old if k != 'room_id'):
            raise ValueError('qr_protection_failed')
    if fingerprint([dict(r) for r in db.execute(text('SELECT * FROM rooms WHERE id BETWEEN 1 AND 8 ORDER BY id')).mappings()]) != report['rooms_hash']:
        raise ValueError('room_protection_failed')
    if history_fingerprint(db) != report['history_hash']:
        raise ValueError('history_protection_failed')
    db.add(AuditLog(actor_type='system', actor_id='QR-PRINTED-BINDING-20261008', store_id=1,
                    action='printed_qr_bindings_corrected', entity_type='service_position_qr',
                    entity_id='3-10', detail=report))
    db.flush()
    db.expire_all()
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
            parser.error('apply requires preview hash and a nonempty regular backup file')
        with backup.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if not args.backup_sha256 or digest != args.backup_sha256:
            parser.error('backup SHA256 mismatch')
    with SessionLocal() as db:
        try:
            if not args.apply and db.bind.dialect.name == 'postgresql':
                db.execute(text('SET TRANSACTION READ ONLY'))
            report = rebind_printed_sofas(db, apply=args.apply, expected_hash=args.expected_hash)
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
