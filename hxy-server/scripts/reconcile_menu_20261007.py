"""Apply the 2026-10-07 image-confirmed menu, preserving unrelated facts."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_, select, text

from app.db.session import SessionLocal
from app.domain.catalog_options import acquire_catalog_mutation_lock, verify_published_catalog_hash
from app.models import AuditLog, MemberPlan, PriceBook, Project, ProjectCatalogVersion
from scripts.reconcile_member_plans_20261008 import PLAN_COPY

VERSION = "menu-20261007"
# Stable codes are historical identifiers, not promises about duration.
# code, name, duration, store cents, member cents, confirmed service flow
MENU = [
    ("hxy-qiqing-30", "现煮草本泡", None, 2990, 2590,
     "AI体质检测+现煮草本泡脚+养生茶饮"),
    ("hxy-xiangxiang-60", "精选草本泡", 60, 9900, 6900,
     "现煮草本泡脚+手臂及足底按摩+刮脚+搓盐（共50分钟）+草本热敷10分钟+养生茶饮"),
    ("hxy-xiaoqi-90", "招牌草本泡", 90, 12900, 8900,
     "现煮草本泡脚+全身按摩（含足部）+刮脚+搓盐（共75分钟）+草本热敷15分钟+养生茶饮"),
    ("hxy-nvshen-60", "女神草本足护", None, 11900, 7900,
     "现煮草本泡脚+去角质刮脚+足部精油按摩+足膜+润足+养生茶饮"),
    ("hxy-tuina-70", "荷小推", 80, 12900, 8900,
     "全身推拿60分钟+艾灸20分钟+养生茶饮+养生零食"),
    ("hxy-spa-60", "舒压SPA", 60, 12900, 8900,
     "现煮草本泡脚+精油SPA45分钟+草本热敷15分钟+养生茶饮+养生零食"),
    ("hxy-spa-90", "安神SPA", 90, 18900, 13900,
     "现煮草本泡脚+精油SPA70分钟+砭石球背部温通10分钟+草本热敷10分钟+养生茶饮+养生零食"),
    ("hxy-taoke-60", "功夫调理", 60, None, 98000,
     "活络油调理20分钟+工具手法20分钟+热敷20分钟（10次/套）"),
    ("hxy-head-30", "头疗", 30, 7900, 4900,
     "头面耳按摩30分钟+经络梳+眼罩/眼贴"),
    ("hxy-caier-30", "采耳", None, 8900, 5900,
     "耳部清洁+耳部按摩"),
    ("hxy-oil-back-30", "精油开背", 30, 9900, 6900,
     "背部精油按摩30分钟"),
    ("hxy-jubu-30", "局部推拿", None, 7900, 4900,
     "肩颈、腰臀、腿部、腹部、足部任选其一"),
    ("hxy-foot-refine-1", "足部精修", None, 6900, 3900,
     "现煮草本泡脚+足部精细护理"),
    ("hxy-cupping-scraping-1", "拔罐/刮痧", None, 5900, 2900,
     "拔罐护理或刮痧护理（任选其一）"),
]

def reconcile_menu(db, *, apply=False, expected_hash=None):
    if apply:
        acquire_catalog_mutation_lock(db)
    query = select(Project).where(Project.store_id == 1, Project.code.in_([row[0] for row in MENU])).order_by(Project.id)
    projects = {p.code: p for p in db.scalars(query.with_for_update() if apply else query)}
    if len(projects) != len(MENU):
        raise ValueError("menu_project_missing")
    plan_query = select(MemberPlan).where(MemberPlan.code.in_(PLAN_COPY)).order_by(MemberPlan.id)
    plans = {p.code: p for p in db.scalars(plan_query.with_for_update() if apply else plan_query)}
    if len(plans) != len(PLAN_COPY):
        raise ValueError("membership_plan_missing")
    now = datetime.now(UTC)
    project_changes, price_changes, plan_changes = [], [], []
    preserved_groups = []
    for code, name, duration, store, member, summary in MENU:
        project = projects[code]
        if project.publication_status != "published":
            raise ValueError("menu_project_not_published")
        if project.detail_modules:
            raise ValueError("menu_custom_detail_requires_review")
        if project.current_published_version_id:
            verify_published_catalog_hash(db, db.get(ProjectCatalogVersion, project.current_published_version_id))
        target = {"name": name, "duration_min": duration, "summary": summary,
                  "price_label": "10次/套" if code == "hxy-taoke-60" else f"{duration}分钟" if duration else "次",
                  "content_version": VERSION}
        if code == "hxy-taoke-60" and "利润款" in (project.tags or []):
            target["tags"] = [tag for tag in project.tags if tag != "利润款"]
        delta = {key: {"before": getattr(project, key), "after": value}
                 for key, value in target.items() if getattr(project, key) != value}
        if delta:
            project_changes.append({"id": project.id, "code": code, "fields": delta})
        price_query = select(PriceBook).where(PriceBook.project_id == project.id,
                      or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now)).order_by(PriceBook.price_type, PriceBook.published_at.desc(), PriceBook.id.desc())
        prices = list(db.scalars(price_query.with_for_update() if apply else price_query))
        preserved_groups.append({"code": code, "rows": [{"id": row.id, "amount_cents": row.amount_cents}
                                                        for row in prices if row.price_type == "group"]})
        for price_type, amount in [("store", store), ("member", member)]:
            active = [row for row in prices if row.price_type == price_type]
            if amount is None:
                if active:
                    raise ValueError("kit_store_price_conflict")
                continue
            if not active or active[0].amount_cents != amount or len(active) > 1:
                price_changes.append({"project_id": project.id, "code": code, "price_type": price_type,
                                      "before": [{"id": row.id, "amount_cents": row.amount_cents} for row in active],
                                      "after": amount})
    for code, (name, price, benefits) in PLAN_COPY.items():
        plan = plans[code]
        target = {"name": name, "price_cents": price, "benefits": benefits}
        delta = {key: {"before": getattr(plan, key), "after": value}
                 for key, value in target.items() if getattr(plan, key) != value}
        if delta:
            plan_changes.append({"id": plan.id, "code": code, "fields": delta})
    report = {"version": VERSION, "changed_projects": len(project_changes), "prices_added": len(price_changes),
              "changed_plans": len(plan_changes), "project_changes": project_changes,
              "price_changes": price_changes, "plan_changes": plan_changes, "preserved_group_prices": preserved_groups,
              "unresolved": ["main_item_pairing_topup_renewal_stacking_manual", "monthly_plan_preserved"]}
    preview_hash = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report["preview_hash"] = preview_hash
    if apply:
        if expected_hash != preview_hash:
            raise ValueError("preview_hash_mismatch")
        if plan_changes:
            raise ValueError("membership_plan_drift")
        for change in project_changes:
            for key, delta in change["fields"].items():
                setattr(projects[change["code"]], key, delta["after"])
        for change in price_changes:
            for before in change["before"]:
                db.get(PriceBook, before["id"]).effective_to = now
            db.add(PriceBook(project_id=change["project_id"], price_type=change["price_type"],
                             amount_cents=change["after"], version=VERSION, publisher="confirmed-menu-20261007", published_at=now))
        if project_changes or price_changes:
            db.add(AuditLog(actor_type="system", actor_id="MENU-20261001", store_id=1,
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
    if args.apply and (not args.expected_hash or not args.backup_reference
                       or not args.backup_reference.is_file() or args.backup_reference.is_symlink()
                       or args.backup_reference.stat().st_size == 0):
        parser.error("--apply requires exact preview hash and a nonempty actual backup")
    if args.apply:
        with args.backup_reference.open("rb") as stream:
            header = stream.read(5)
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not args.backup_sha256 or digest != args.backup_sha256:
            parser.error("backup SHA256 mismatch")
        if header != b"PGDMP":
            parser.error("apply requires an actual PostgreSQL custom-format dump")
    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '30s'"))
            report = reconcile_menu(db, apply=args.apply, expected_hash=args.expected_hash)
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
