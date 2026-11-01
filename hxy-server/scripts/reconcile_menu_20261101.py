"""Reconcile the approved menu using an exact preview and a verified database backup."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_, select, text

from app.db.session import SessionLocal
from app.domain.catalog_options import acquire_catalog_mutation_lock, verify_published_catalog_hash
from app.models import AuditLog, PriceBook, Project, ProjectCatalogVersion, Store

VERSION = "menu-20261101"
CONTENT = Path(__file__).resolve().parents[1] / "content/menu/menu-20261101.json"
RETIRED = ("hxy-qiqing-30", "hxy-tuina-70", "hxy-taoke-60")
SOURCE_SHA = "1e0be09e050781316a23ff2054967d71af141a177b7da7dc477f144ef2f7d715"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_menu():
    data = json.loads(CONTENT.read_text())
    assert data["version"] == VERSION and data["source_sha256"] == SOURCE_SHA
    assert data["status"] == "approved_for_release" and data["approval_reference"]
    items = data["items"]
    assert len(items) == len({p["code"] for p in items}) == 14
    assert sum(p["existing_code"] is None for p in items) == 3
    for item in items:
        if item["bundle_cents"] is not None:
            assert item["bundle_cents"] == 128000 and item["bundle_sessions"] == 10
            assert item["store_cents"] is None and item["member_cents"] is None
        else:
            assert all(type(item[k]) is int and item[k] > 0 for k in ("store_cents", "member_cents"))
    return data


def reconcile_menu(db, *, apply=False, expected_hash=None):
    menu = load_menu()
    if apply:
        acquire_catalog_mutation_lock(db)
    store = db.get(Store, 1)
    if store is None or store.store_code != "hxy-anyang-ziwei-001":
        raise ValueError("menu_store_identity_mismatch")
    codes = [p["code"] for p in menu["items"]] + list(RETIRED)
    query = select(Project).where(Project.code.in_(codes)).order_by(Project.id)
    projects = {p.code: p for p in db.scalars(query.with_for_update() if apply else query)}
    if any(p.store_id != 1 for p in projects.values()):
        raise ValueError("menu_project_store_conflict")
    for item in menu["items"]:
        if item["existing_code"] and item["code"] not in projects:
            raise ValueError("existing_menu_project_missing")
        current = projects.get(item["code"])
        if current and item["existing_code"] is None and current.content_version != VERSION:
            raise ValueError("new_menu_code_conflict")
        if current and current.current_published_version_id:
            verify_published_catalog_hash(db, db.get(ProjectCatalogVersion, current.current_published_version_id))
        if current and current.detail_modules and current.content_version != VERSION:
            raise ValueError("custom_detail_requires_review")
    if not all(code in projects for code in RETIRED):
        raise ValueError("retired_menu_project_missing")
    now = datetime.now(UTC)
    project_changes, price_changes = [], []
    for item in menu["items"]:
        project = projects.get(item["code"])
        bundle = item["bundle_cents"] is not None
        target = {
            "name": item["name"], "duration_min": item["duration_min"], "summary": item["summary"],
            "category": item["project_category"], "category_mark": item["category_mark"],
            "display_order": item["display_order"], "price_label": "10次/套" if bundle else (f'{item["duration_min"]}分钟' if item["duration_min"] else "1次"),
            "content_version": VERSION, "independently_visible": True, "publication_status": "published",
            "tags": [item["badge"]] if item["badge"] else [],
        }
        if not project:
            target["image_url"] = "/diy/assets/service-tuina.jpg"
        delta = {key: {"before": getattr(project, key) if project else None, "after": value}
                 for key, value in target.items() if project is None or getattr(project, key) != value}
        if delta:
            project_changes.append({"code": item["code"], "id": project.id if project else None, "fields": delta})
        price_query = select(PriceBook).where(
            PriceBook.project_id == project.id,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now)
        ).order_by(PriceBook.id) if project else None
        prices = list(db.scalars(price_query.with_for_update() if apply else price_query)) if project else []
        targets = {"store": item["bundle_cents"]} if bundle else {"store": item["store_cents"], "member": item["member_cents"]}
        for kind, amount in targets.items():
            active = [p for p in prices if p.price_type == kind]
            if len(active) != 1 or active[0].amount_cents != amount:
                price_changes.append({"code": item["code"], "price_type": kind, "after": amount,
                                      "before": [{"id": p.id, "amount_cents": p.amount_cents} for p in active]})
    for code in RETIRED:
        p = projects[code]
        target = {"publication_status": "archived", "independently_visible": False}
        delta = {key: {"before": getattr(p, key), "after": value} for key, value in target.items() if getattr(p, key) != value}
        if delta:
            project_changes.append({"code": code, "id": p.id, "fields": delta})
    report = {"version": VERSION, "source_sha256": SOURCE_SHA,
              "content_sha256": hashlib.sha256(CONTENT.read_bytes()).hexdigest(),
              "store_id": 1, "project_changes": project_changes, "price_changes": price_changes,
              "new_projects": sum(c["id"] is None for c in project_changes),
              "group_prices_preserved": True, "option_versions_preserved": True,
              "member_plans_preserved": True}
    report["preview_hash"] = fingerprint(report)
    if apply:
        if expected_hash != report["preview_hash"]:
            raise ValueError("menu_preview_changed")
        for change in project_changes:
            project = projects.get(change["code"])
            if project is None:
                project = Project(store_id=1, code=change["code"], detail_modules=[], diy_options=[])
                db.add(project)
                projects[change["code"]] = project
            for key, delta in change["fields"].items():
                setattr(project, key, delta["after"])
        db.flush()
        for change in price_changes:
            for before in change["before"]:
                db.get(PriceBook, before["id"]).effective_to = now
            db.add(PriceBook(project_id=projects[change["code"]].id, price_type=change["price_type"],
                             amount_cents=change["after"], version=VERSION,
                             publisher="confirmed-menu-20261101", published_at=now))
        if project_changes or price_changes:
            db.add(AuditLog(actor_type="system", actor_id="MENU-20261101", store_id=1,
                            action="confirmed_menu_reconciled", entity_type="menu", entity_id=VERSION, detail=report))
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
            report = reconcile_menu(db, apply=args.apply, expected_hash=args.expected_hash)
            db.commit() if args.apply else db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
