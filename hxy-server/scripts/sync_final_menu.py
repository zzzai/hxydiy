"""幂等同步已确认菜单到指定门店；不删除价格历史，也不改动选项目录。"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import PriceBook, Project, Store
from app.seed import PROJECTS


def sync_final_menu(db: Session, store_id: int, *, apply: bool = False) -> dict[str, int]:
    store = db.get(Store, store_id)
    if store is None:
        raise ValueError(f"门店不存在: {store_id}")
    created = updated = prices_added = 0
    sync_at = datetime.now(UTC)
    for display_order, (code, category, mark, name, duration, summary, store_price, group_price, member_price, image, label) in enumerate(PROJECTS):
        project = db.scalar(select(Project).where(Project.store_id == store_id, Project.code == code))
        if project is None:
            project = Project(store_id=store_id, code=code)
            db.add(project)
            created += 1
        for key, value in {
            "category": category, "category_mark": mark, "name": name, "duration_min": duration,
            "summary": summary, "image_url": image, "price_label": label,
            "tags": [label], "display_order": display_order,
            "publication_status": "published", "content_version": "menu-20260820",
        }.items():
            setattr(project, key, value)
        db.flush()
        for price_type, amount in (("store", store_price), ("group", group_price), ("member", member_price)):
            active_rows = list(db.scalars(select(PriceBook).where(
                PriceBook.project_id == project.id,
                PriceBook.price_type == price_type,
                or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > sync_at),
            ).order_by(PriceBook.published_at.desc(), PriceBook.id.desc())))
            if amount is None:
                for active in active_rows:
                    active.effective_to = sync_at
                    updated += 1
                continue
            latest = active_rows[0] if active_rows else None
            if latest is None or latest.amount_cents != amount:
                for active in active_rows:
                    active.effective_to = sync_at
                db.add(PriceBook(project_id=project.id, price_type=price_type, amount_cents=amount,
                                  version="menu-20260820", publisher="menu-sheet-sync", published_at=sync_at))
                prices_added += 1
                updated += int(latest is not None)
    if apply:
        db.commit()
    else:
        db.rollback()
    return {"created": created, "updated": updated, "prices_added": prices_added}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(sync_final_menu(db, args.store_id, apply=args.apply))


if __name__ == "__main__":
    main()
