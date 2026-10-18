from sqlalchemy import select, union
from sqlalchemy.orm import Session

from app.models.scrm import CustomerTag, CustomerTagRelation
from app.models.customer_tag_contribution import CustomerTagContribution


def tagged_user_ids(store_id: int, tag_ids):
    scoped_tags = select(CustomerTag.id).where(CustomerTag.store_id == store_id, CustomerTag.id.in_(tag_ids))
    return union(
        select(CustomerTagRelation.user_id).where(CustomerTagRelation.tag_id.in_(scoped_tags)),
        select(CustomerTagContribution.user_id).where(CustomerTagContribution.store_id == store_id, CustomerTagContribution.tag_id.in_(scoped_tags), CustomerTagContribution.revoked_at.is_(None)),
    )


def customer_tag_ids(store_id: int, user_id: int):
    return union(
        select(CustomerTagRelation.tag_id).join(CustomerTag, CustomerTag.id == CustomerTagRelation.tag_id).where(CustomerTagRelation.user_id == user_id, CustomerTag.store_id == store_id),
        select(CustomerTagContribution.tag_id).where(CustomerTagContribution.store_id == store_id, CustomerTagContribution.user_id == user_id, CustomerTagContribution.revoked_at.is_(None)),
    )


def operational_tag_view(db: Session, store_id: int, user_id: int, staff_id: int):
    tags = db.scalars(select(CustomerTag).where(CustomerTag.store_id == store_id, CustomerTag.status == "active", CustomerTag.id.in_(customer_tag_ids(store_id, user_id))).order_by(CustomerTag.id)).all()
    items = []
    for tag in tags:
        sources = []
        if db.scalar(select(CustomerTagRelation.id).where(CustomerTagRelation.user_id == user_id, CustomerTagRelation.tag_id == tag.id).limit(1)):
            sources.append({"kind": "legacy", "contribution_id": None, "owned_by_me": False, "version": None})
        contributions = db.scalars(select(CustomerTagContribution).where(CustomerTagContribution.store_id == store_id, CustomerTagContribution.user_id == user_id, CustomerTagContribution.tag_id == tag.id, CustomerTagContribution.revoked_at.is_(None)).order_by(CustomerTagContribution.id)).all()
        sources.extend({"kind": "contribution", "contribution_id": c.id, "owned_by_me": c.created_by_staff_id == staff_id, "version": c.version} for c in contributions)
        items.append({"id": tag.id, "name": tag.name, "color": tag.color, "sources": sources})
    options = db.scalars(select(CustomerTag).where(CustomerTag.store_id == store_id, CustomerTag.status == "active", CustomerTag.tag_type == "manual").order_by(CustomerTag.id)).all()
    return {"items": items, "available_tags": [{"id": t.id, "name": t.name, "color": t.color} for t in options]}
