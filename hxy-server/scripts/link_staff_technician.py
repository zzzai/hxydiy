"""Preview or apply linking an existing store manager account to a technician profile.

The store manager is a technician with extra store permissions. The WeCom
provisioning tool creates the manager login, while the technician profile is
created in the admin UI; this controlled step links the two without changing
either role or store scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import AuditLog, Staff, Technician


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_staff(db, *, staff_id: int | None, store_id: int | None, username: str | None, lock: bool) -> Staff:
    query = select(Staff)
    if staff_id is not None:
        query = query.where(Staff.id == staff_id)
    else:
        if store_id is None or not username:
            raise ValueError("需要 staff_id，或 store_id + username")
        query = query.where(Staff.store_id == store_id, Staff.username == username)
    if lock:
        query = query.with_for_update()
    staff = db.scalar(query)
    if staff is None:
        raise ValueError("员工账号不存在")
    return staff


def build_plan(
    db,
    *,
    staff_id: int | None = None,
    store_id: int | None = None,
    username: str | None = None,
    technician_code: str,
    lock: bool = False,
) -> dict:
    staff = _find_staff(db, staff_id=staff_id, store_id=store_id, username=username, lock=lock)
    if staff.status != "active":
        raise ValueError("员工账号未启用")
    if staff.role != "manager":
        raise ValueError("只有店长账号可以绑定技师档案")
    if staff.store_id is None:
        raise ValueError("店长账号必须绑定门店")

    query = select(Technician).where(Technician.code == technician_code)
    if lock:
        query = query.with_for_update()
    technician = db.scalar(query)
    if technician is None:
        raise ValueError("技师档案不存在")
    if technician.store_id != staff.store_id:
        raise ValueError("技师档案与店长不属于同一门店")
    if technician.status == "resigned":
        raise ValueError("已离职技师不能绑定")

    if staff.technician_id not in (None, technician.id):
        raise ValueError("店长已绑定其他技师档案")
    other = db.scalar(select(Staff).where(
        Staff.technician_id == technician.id,
        Staff.id != staff.id,
    ))
    if other is not None:
        raise ValueError("该技师档案已被其他员工绑定")

    identity = {
        "staff_id": staff.id,
        "store_id": staff.store_id,
        "technician_id": technician.id,
        "technician_code": technician.code,
    }
    return {
        **identity,
        "staff_username": staff.username,
        "staff_name": staff.name,
        "technician_name": technician.name,
        "action": "unchanged" if staff.technician_id == technician.id else "link",
        "before_technician_id": staff.technician_id,
        "preview_hash": fingerprint(identity),
    }


def apply_plan(db, plan: dict) -> dict:
    expected = plan.get("preview_hash")
    current = build_plan(
        db,
        staff_id=plan["staff_id"],
        technician_code=plan["technician_code"],
        lock=True,
    )
    if not expected or current["preview_hash"] != expected:
        raise ValueError("预览已变化，请重新生成预览")
    staff = db.get(Staff, plan["staff_id"])
    if staff is None:
        raise ValueError("员工账号不存在")
    if current["action"] == "unchanged":
        return {**current, "action": "unchanged"}
    before = staff.technician_id
    staff.technician_id = current["technician_id"]
    db.add(AuditLog(
        actor_type="system",
        actor_id="STORE-TEAM",
        action="staff_technician_linked",
        entity_type="staff",
        entity_id=str(staff.id),
        store_id=staff.store_id,
        detail={
            "staff_id": staff.id,
            "username": staff.username,
            "technician_id": current["technician_id"],
            "technician_code": current["technician_code"],
            "before_technician_id": before,
            "after_technician_id": current["technician_id"],
            "preview_hash": expected,
        },
    ))
    db.flush()
    return {**current, "action": "linked"}


def _check_backup(path: Path | None, sha256: str | None) -> None:
    if path is None or not path.is_file() or path.is_symlink():
        raise ValueError("apply 需要真实备份文件")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("需要 PostgreSQL custom-format 备份")
        stream.seek(0)
        if hashlib.file_digest(stream, "sha256").hexdigest() != sha256:
            raise ValueError("备份摘要不匹配")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staff-id", type=int)
    parser.add_argument("--store-id", type=int)
    parser.add_argument("--username")
    parser.add_argument("--technician-code", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--backup-reference", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()

    if args.apply:
        if not args.expected_hash:
            parser.error("apply requires --expected-hash")
        _check_backup(args.backup_reference, args.backup_sha256)

    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '30s'"))
            plan = build_plan(
                db,
                staff_id=args.staff_id,
                store_id=args.store_id,
                username=args.username,
                technician_code=args.technician_code,
                lock=False,
            )
            if args.apply:
                result = apply_plan(db, {**plan, "preview_hash": args.expected_hash})
                db.commit()
                print(json.dumps(result, ensure_ascii=False))
            else:
                db.rollback()
                print(json.dumps(plan, ensure_ascii=False))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
