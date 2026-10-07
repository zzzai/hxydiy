"""Relabel the eight existing store-1 sofa positions; dry-run by default."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import AuditLog, Room

OLD = [1, 2, 3, 5, 6, 7, 8, 9]
NEW = [5, 3, 2, 1, 9, 8, 7, 6]


def relabel_sofas(db, *, apply=False, restore=False):
    # Lock all store positions to check label collisions before any write.
    query = select(Room).where(Room.store_id == 1).order_by(Room.id)
    rooms = list(db.scalars(query.with_for_update() if apply else query))
    targets = [room for room in rooms if 1 <= room.id <= 8]
    if len(targets) != 8:
        raise ValueError("seat_mapping_missing")
    for i, room in enumerate(targets):
        if (room.id != i + 1 or room.code != f"sofa-{i + 1:02}"
                or room.room_type != "sofa" or not room.is_service_position
                or room.is_space_container
                or abs(room.map_x - (0.08 if i < 4 else 0.7)) > 1e-6
                or abs(room.map_y - [0.14, 0.34, 0.54, 0.74][i % 4]) > 1e-6):
            raise ValueError("seat_mapping_drift")
    labels = [room.customer_label for room in targets]
    if labels not in [[f"{n}号沙发" for n in OLD], [f"{n}号沙发" for n in NEW]]:
        raise ValueError("seat_labels_drift")
    if any(room.name != room.customer_label for room in targets):
        raise ValueError("seat_names_drift")
    desired = [f"{n}号沙发" for n in (OLD if restore else NEW)]
    if any(room.id > 8 and (room.name in desired or room.customer_label in desired)
           for room in rooms):
        raise ValueError("seat_label_collision")
    changes = [{"id": room.id, "code": room.code, "before": room.name, "after": label}
               for room, label in zip(targets, desired) if room.name != label]
    if apply:
        for change in changes:
            # Do not invoke ORM timestamp/version or service-state updates.
            db.execute(text("UPDATE rooms SET name=:label, customer_label=:label WHERE id=:id AND store_id=1"),
                       {"id": change["id"], "label": change["after"]})
        if changes:
            db.add(AuditLog(actor_type="system", actor_id="SEAT-LABEL-20261007",
                            store_id=1, action="service_position_labels_restored" if restore else
                            "service_position_labels_updated", entity_type="room", entity_id="1-8",
                            detail={"changes": changes}))
        db.flush()
        db.expire_all()
    return {"apply": apply, "restore": restore, "changed": len(changes), "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--backup-reference", type=Path,
                        help="Existing verified backup inside the executing container")
    args = parser.parse_args()
    if args.apply and (not args.backup_reference or not args.backup_reference.is_file()
                       or args.backup_reference.is_symlink() or args.backup_reference.stat().st_size == 0):
        parser.error("--apply requires a nonempty verified backup reference")
    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '30s'"))
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
            report = relabel_sofas(db, apply=args.apply, restore=args.restore)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
