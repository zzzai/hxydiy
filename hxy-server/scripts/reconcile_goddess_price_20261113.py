"""Apply the approved Goddess store price through an exact, append-only preview."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from app.api.admin_v2 import _append_project_prices
from app.db.session import SessionLocal
from app.domain.catalog_options import acquire_catalog_mutation_lock
from app.models import AuditLog, PriceBook, Project, Store

VERSION = "goddess-price-20261113"
CODE = "hxy-nvshen-60"


def snapshot(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def reconcile_price(db, *, apply=False, expected_hash=None):
    if apply:
        acquire_catalog_mutation_lock(db)
    query = select(Project).where(Project.code == CODE)
    project = db.scalar(query.with_for_update() if apply else query)
    store = db.get(Store, 1)
    if (not project or project.store_id != 1 or not store
            or store.store_code != "hxy-anyang-ziwei-001"
            or project.publication_status != "published" or project.category != "bath"):
        raise ValueError("goddess_project_scope_changed")
    query = select(PriceBook).where(PriceBook.project_id == project.id).order_by(PriceBook.id)
    rows = list(db.scalars(query.with_for_update() if apply else query))
    now = datetime.now(UTC)
    current = [row for row in rows if row.effective_to is None
               or row.effective_to.replace(tzinfo=UTC) > now]
    prices = {row.price_type: row.amount_cents for row in current}
    if (len(current) != 3 or prices.get("store") not in {10900, 11900}
            or prices.get("member") != 7900 or prices.get("group") != 8900):
        raise ValueError("goddess_price_baseline_changed")
    report = {"version": VERSION, "project_id": project.id, "store_id": 1,
              "project_code": CODE, "before_cents": prices, "target_store_cents": 11900,
              "change_count": int(prices["store"] != 11900),
              "baseline_sha256": fingerprint({"project": snapshot(project), "prices": [snapshot(row) for row in rows]})}
    report["preview_hash"] = fingerprint(report)
    if apply:
        if expected_hash != report["preview_hash"]:
            raise ValueError("goddess_price_preview_changed")
        if report["change_count"]:
            _append_project_prices(db, project.id, {"store": 11900}, VERSION)
            db.add(AuditLog(actor_type="system", actor_id=VERSION, store_id=1,
                            action="approved_project_price_changed", entity_type="project",
                            entity_id=str(project.id), detail=report))
            db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--backup-reference", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()
    if args.apply:
        path = args.backup_reference
        if not args.expected_hash or not path or path.is_symlink() or not path.is_file():
            parser.error("apply requires exact preview and an actual backup")
        with path.open("rb") as stream:
            if stream.read(5) != b"PGDMP":
                parser.error("PostgreSQL custom-format backup required")
            stream.seek(0)
            if hashlib.file_digest(stream, "sha256").hexdigest() != args.backup_sha256:
                parser.error("backup digest mismatch")
    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '30s'"))
            report = reconcile_price(db, apply=args.apply, expected_hash=args.expected_hash)
            db.commit() if args.apply else db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
