"""Reconcile store 1's auxiliary menu without rewriting historical snapshots.

Dry-run by default. Run with --apply only after the schema migration and backup.
"""

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.catalog_options import CatalogDomainError, _snapshot_hash, verify_published_catalog_hash
from app.models import (
    AuditLog, PriceBook, Project, ProjectCatalogVersion, ProjectOptionChoice,
    ProjectOptionGroup, Store,
)


EXISTING = {
    "hxy-head-30": ("头疗", 7900, 4900, 7),
    "hxy-foot-refine-1": ("足部精修", 6900, 3900, 8),
    "hxy-caier-30": ("采耳", 8900, 5900, 10),
    "hxy-jubu-30": ("局部推拿", 7900, 4900, 11),
    "hxy-baguan-1": ("拔罐", 5900, 2900, None),
    "hxy-guasha-1": ("刮痧", 5900, 2900, None),
}
NEW = {
    "hxy-oil-back-30": ("精油开背", 9900, 6900, 9, 30, "背部精油按摩30分钟", "/assets/projects/hxy-spa-60.webp"),
    "hxy-cupping-scraping-1": ("拔罐/刮痧", 5900, 2900, 12, None, "拔罐护理或刮痧护理（任选其一）", "/assets/hxy-mascot.webp"),
}


def _current_price(db: Session, project_id: int, price_type: str) -> int | None:
    row = db.scalar(select(PriceBook).where(
        PriceBook.project_id == project_id,
        PriceBook.price_type == price_type,
        (PriceBook.effective_to.is_(None) | (PriceBook.effective_to > datetime.now(UTC))),
    ).order_by(PriceBook.published_at.desc(), PriceBook.id.desc()))
    return row.amount_cents if row else None


def _add_price(db: Session, project_id: int, price_type: str, amount: int) -> None:
    now = datetime.now(UTC)
    for row in db.scalars(select(PriceBook).where(
        PriceBook.project_id == project_id, PriceBook.price_type == price_type,
        (PriceBook.effective_to.is_(None) | (PriceBook.effective_to > now)),
    )):
        row.effective_to = now
    db.add(PriceBook(project_id=project_id, price_type=price_type,
                     amount_cents=amount, publisher="aux-menu-reconcile", published_at=now))


def _verify_combined_options(db: Session, project: Project) -> None:
    version = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if version is None or version.project_id != project.id or version.status != "published":
        raise ValueError("unexpected_combined_options")
    try:
        verify_published_catalog_hash(db, version)
    except CatalogDomainError as exc:
        raise ValueError("unexpected_combined_options") from exc
    groups = list(db.scalars(select(ProjectOptionGroup).where(ProjectOptionGroup.catalog_version_id == version.id)))
    if len(groups) != 1:
        raise ValueError("unexpected_combined_options")
    group = groups[0]
    choices = list(db.scalars(select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == group.id)))
    if (group.code != "care_method" or group.selection_mode != "single" or not group.required
        or group.min_select != 1 or group.max_select != 1
        or {(choice.code, choice.name, choice.choice_type, choice.charge_mode, choice.status) for choice in choices}
        != {("cupping", "拔罐护理", "preference", "free", "active"),
            ("scraping", "刮痧护理", "preference", "free", "active")}):
        raise ValueError("unexpected_combined_options")


def ensure_combined_options(db: Session, project: Project) -> None:
    if project.current_published_version_id is not None:
        _verify_combined_options(db, project)
        return
    version = ProjectCatalogVersion(project_id=project.id, version=1, status="published")
    db.add(version)
    db.flush()
    project.current_published_version_id = version.id
    group = ProjectOptionGroup(catalog_version_id=version.id, code="care_method",
                               name="护理方式", selection_mode="single", required=True,
                               min_select=1, max_select=1)
    db.add(group)
    db.flush()
    for index, (choice_code, choice_name) in enumerate((("cupping", "拔罐护理"), ("scraping", "刮痧护理"))):
        db.add(ProjectOptionChoice(option_group_id=group.id, code=choice_code,
                                   name=choice_name, choice_type="preference",
                                   charge_mode="free", display_order=index))
    db.flush()
    version.snapshot_hash = _snapshot_hash(db, version.id)


def reconcile_store(db: Session, store_id: int, *, apply: bool = False) -> dict:
    if not db.get(Store, store_id):
        raise ValueError("store_not_found")
    unexpected = set(db.scalars(select(Project.code).where(
        Project.store_id == store_id, Project.category_mark == "辅",
    ))) - EXISTING.keys() - NEW.keys()
    if unexpected:
        raise ValueError("unexpected_aux_project")
    projects = {p.code: p for p in db.scalars(select(Project).where(
        Project.store_id == store_id, Project.code.in_([*EXISTING, *NEW]),
    ))}
    if any(code not in projects for code in EXISTING):
        raise ValueError("existing_aux_project_missing")
    changes = []
    for code, (name, store_price, member_price, order) in EXISTING.items():
        project = projects[code]
        if project.name != name or project.publication_status != "published" or project.category_mark != "辅":
            raise ValueError(f"unexpected_project_state:{code}")
        current_store = _current_price(db, project.id, "store")
        current_member = _current_price(db, project.id, "member")
        allowed_store = {store_price, 5900} if code == "hxy-foot-refine-1" else {store_price}
        if current_store not in allowed_store or current_member != member_price:
            raise ValueError(f"unexpected_project_price:{code}")
        if current_store != store_price:
            changes.append(f"update_store_price:{code}")
            if apply:
                _add_price(db, project.id, "store", store_price)
        visible = code not in {"hxy-baguan-1", "hxy-guasha-1"}
        if project.independently_visible != visible:
            changes.append(f"set_visibility:{code}:{visible}")
            if apply:
                project.independently_visible = visible
        if order is not None and project.display_order != order:
            changes.append(f"set_display_order:{code}:{order}")
            if apply:
                project.display_order = order
        if code == "hxy-jubu-30" and project.summary != "肩颈、腰背、腿部、腹部、足部（任选其一）":
            changes.append("update_summary:hxy-jubu-30")
            if apply:
                project.summary = "肩颈、腰背、腿部、腹部、足部（任选其一）"
    for code, (name, store_price, member_price, order, duration, summary, image_url) in NEW.items():
        project = projects.get(code)
        if project is None:
            changes.append(f"create_project:{code}")
            if not apply:
                continue
            project = Project(store_id=store_id, code=code, category="small", category_mark="辅",
                              name=name, duration_min=duration, summary=summary, image_url=image_url,
                              display_order=order, price_label="按次" if duration is None else "小项",
                              publication_status="published", independently_visible=True,
                              content_version="aux-menu-20260924")
            db.add(project)
            db.flush()
            _add_price(db, project.id, "store", store_price)
            _add_price(db, project.id, "member", member_price)
            if code == "hxy-cupping-scraping-1":
                ensure_combined_options(db, project)
        elif (project.name != name or project.store_id != store_id or project.publication_status != "published"
              or project.category_mark != "辅" or project.display_order != order
              or project.duration_min != duration or project.summary != summary
              or not project.independently_visible or _current_price(db, project.id, "store") != store_price
              or _current_price(db, project.id, "member") != member_price):
            raise ValueError(f"unexpected_new_project_state:{code}")
        elif code == "hxy-cupping-scraping-1":
            _verify_combined_options(db, project)
    if apply and changes:
        db.add(AuditLog(actor_type="system", actor_id="aux-menu-reconcile", store_id=store_id,
                        action="aux_menu_reconciled", entity_type="project", entity_id=str(store_id),
                        detail={"changes": changes}))
    return {"store_id": store_id, "changes": changes, "applied": apply}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        report = reconcile_store(db, args.store_id, apply=args.apply)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
