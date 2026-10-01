"""Preview, apply or compensate the confirmed menu; never rewrite order snapshots."""

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from app.api.admin import _current_staff
from app.db.session import SessionLocal
from app.domain.catalog_options import acquire_catalog_mutation_lock, lock_catalog_projects
from app.domain.confirmed_menu import MENU, MENU_VERSION, RETIRED_CODES, contract_modules, menu_spec
from app.models import AuditLog, PriceBook, Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup, Store


FIELDS = ("name", "category", "category_mark", "duration_min", "summary", "price_label", "display_order",
          "independently_visible", "publication_status", "content_version", "detail_modules")
CODES = {row[0] for row in MENU} | RETIRED_CODES


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def state(db, project):
    if project is None:
        return None
    rows = list(db.scalars(select(PriceBook).where(PriceBook.project_id == project.id,
        (PriceBook.effective_to.is_(None) | (PriceBook.effective_to > datetime.now(UTC))))
        .order_by(PriceBook.published_at.desc(), PriceBook.id.desc())))
    prices = {}
    for row in rows:
        prices.setdefault(row.price_type, row.amount_cents)
    return {"id": project.id, "fields": {key: deepcopy(getattr(project, key)) for key in FIELDS},
            "prices": prices, "price_rows": [{"id": row.id, "type": row.price_type,
                                                "amount": row.amount_cents, "version": row.version} for row in rows]}


def states(db, store_id):
    return {project.code: state(db, project) for project in db.scalars(select(Project).where(
        Project.store_id == store_id, Project.code.in_(CODES)).order_by(Project.code))}


def plan_menu(db, store_id, *, rollback_audit=None):
    if db.get(Store, store_id) is None:
        raise ValueError("unknown store")
    before = states(db, store_id)
    desired = {}
    if rollback_audit is not None:
        audit = db.get(AuditLog, rollback_audit)
        if audit is None or audit.store_id != store_id or audit.action != "apply_confirmed_menu":
            raise ValueError("unknown menu application audit")
        previous_compensation = db.scalar(select(AuditLog).where(
            AuditLog.store_id == store_id, AuditLog.action == "compensate_confirmed_menu",
            AuditLog.detail["rollback_audit"].as_integer() == rollback_audit,
        ).order_by(AuditLog.id.desc()))
        if previous_compensation and digest(before) == previous_compensation.detail["after_sha256"]:
            desired = {code: {"fields": record["fields"], "prices": record["prices"]} for code, record in before.items()}
        elif digest(before) != audit.detail["after_sha256"]:
            raise ValueError("menu changed since application; compensation requires renewed review")
        else:
            for code, record in audit.detail["before"].items():
                desired[code] = {"fields": record["fields"], "prices": record["prices"]}
            for code in before.keys() - audit.detail["before"].keys():
                desired[code] = {"fields": {**before[code]["fields"], "publication_status": "archived",
                                            "independently_visible": False}, "prices": {}}
    else:
        for order, row in enumerate(MENU):
            code, name, category, duration, amounts, flow = row
            old = before.get(code)
            fields = deepcopy(old["fields"]) if old else {}
            spec = menu_spec(row)
            fields.update(name=name, category=category, category_mark="辅" if category in {"small", "local-strength"} else fields.get("category_mark", ""),
                          duration_min=duration, summary=flow + ("；已含1次现煮草本泡" if spec["included_services"] else ""),
                          price_label="10次/套，每次60分钟" if code == "hxy-taoke-60" else "单次服务" if duration is None else "组合服务",
                          display_order=order, independently_visible=True, publication_status="published",
                          content_version=MENU_VERSION, detail_modules=contract_modules(fields.get("detail_modules"), spec))
            desired[code] = {"fields": fields, "prices": {kind: amount for kind, amount in zip(("store", "group", "member"), amounts) if amount is not None}}
        for code in RETIRED_CODES & before.keys():
            identifier = before[code]["id"]
            referrers = db.scalars(select(ProjectCatalogVersion.project_id).join(ProjectOptionGroup,
                ProjectOptionGroup.catalog_version_id == ProjectCatalogVersion.id).join(ProjectOptionChoice,
                ProjectOptionChoice.option_group_id == ProjectOptionGroup.id).where(
                ProjectCatalogVersion.status == "published", ProjectOptionChoice.linked_project_id == identifier)).all()
            if referrers:
                raise ValueError(f"retired project has published catalog references: {code}")
            desired[code] = {"fields": {**before[code]["fields"], "publication_status": "archived", "independently_visible": False},
                             "prices": before[code]["prices"]}
    changes = [{"code": code, "id": before[code]["id"] if code in before else None, **target}
               for code, target in sorted(desired.items()) if code not in before or target["fields"] != before[code]["fields"] or target["prices"] != before[code]["prices"]]
    result = {"store_id": store_id, "version": MENU_VERSION, "rollback_audit": rollback_audit,
              "before": before, "changes": changes}
    result["plan_sha256"] = digest(result)
    return result


def authorize(db, token, store_id):
    staff = _current_staff("Bearer " + token, db)
    require_scope(staff, store_id)
    return staff


def require_scope(staff, store_id):
    if staff.status != "active":
        raise ValueError("active staff required")
    if not (staff.role == "admin" and staff.store_id is None):
        raise ValueError("headquarters catalog administrator required")


def apply_menu(db, store_id, staff, expected_plan, *, rollback_audit=None):
    require_scope(staff, store_id)
    # Same advisory lock and ascending row locks as catalog administration.
    acquire_catalog_mutation_lock(db)
    ids = list(db.scalars(select(Project.id).where(Project.store_id == store_id)))
    lock_catalog_projects(db, ids)
    plan = plan_menu(db, store_id, rollback_audit=rollback_audit)
    if not plan["changes"]:
        return {"changed": 0, "plan_sha256": plan["plan_sha256"], "audit_id": None}
    if expected_plan != plan["plan_sha256"]:
        raise ValueError("preview changed; no writes applied")
    now = datetime.now(UTC)
    for change in plan["changes"]:
        project = db.get(Project, change["id"]) if change["id"] else None
        if project is None:
            if db.scalar(select(Project).where(Project.code == change["code"])) is not None:
                raise ValueError("project code belongs to another store")
            project = Project(store_id=store_id, code=change["code"], image_url="/assets/services/service-foot-bath.jpg")
            db.add(project)
        for key, value in change["fields"].items():
            setattr(project, key, deepcopy(value))
        db.flush()
        old = plan["before"].get(change["code"], {}).get("prices", {})
        for kind in old.keys() | change["prices"].keys():
            amount = change["prices"].get(kind)
            if old.get(kind) == amount:
                continue
            for row in db.scalars(select(PriceBook).where(PriceBook.project_id == project.id,
                PriceBook.price_type == kind, (PriceBook.effective_to.is_(None) | (PriceBook.effective_to > now)))):
                row.effective_to = now
            if amount is not None:
                db.add(PriceBook(project_id=project.id, price_type=kind, amount_cents=amount,
                    version=MENU_VERSION, publisher="confirmed-menu-compensation" if rollback_audit else "confirmed-menu", published_at=now))
    db.flush()
    after = states(db, store_id)
    audit = AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=store_id,
        action="compensate_confirmed_menu" if rollback_audit else "apply_confirmed_menu", entity_type="store", entity_id=str(store_id),
        detail={"version": MENU_VERSION, "plan_sha256": expected_plan, "before": plan["before"],
                "after_sha256": digest(after), "rollback_audit": rollback_audit})
    db.add(audit)
    db.flush()
    return {"changed": len(plan["changes"]), "plan_sha256": expected_plan, "audit_id": audit.id,
            "project_ids": {code: record["id"] for code, record in after.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--store-code", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan")
    parser.add_argument("--rollback-audit", type=int)
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()
    token = os.environ.get("HXY_STAFF_TOKEN", "")
    if args.apply:
        if not args.expected_plan or not args.backup_file or not args.backup_file.is_file() or args.backup_file.stat().st_size == 0:
            parser.error("apply requires preview SHA and a verified backup")
        with args.backup_file.open("rb") as backup:
            if hashlib.file_digest(backup, "sha256").hexdigest() != args.backup_sha256:
                parser.error("backup SHA256 mismatch")
    try:
        with SessionLocal() as db:
            store = db.get(Store, args.store_id)
            if store is None or store.store_code != args.store_code:
                raise ValueError("store ID/code mismatch")
            staff = authorize(db, token, store.id)
            report = apply_menu(db, store.id, staff, args.expected_plan, rollback_audit=args.rollback_audit) if args.apply else plan_menu(db, store.id, rollback_audit=args.rollback_audit)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        print(json.dumps(report, ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    except (HTTPException, SQLAlchemyError):
        parser.exit(1, "menu operation rejected; no sensitive diagnostics displayed\n")


if __name__ == "__main__":
    main()
