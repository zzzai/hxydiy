"""Store lifecycle guards shared by customer-facing transaction endpoints."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, PageContent, PositionOccupancy, Project, Room, Store

OPEN_STORE_STATUSES = frozenset({"open", "trial_open"})
STORE_STATUS_LABELS = {
    "draft": "未建档",
    "preparing": "筹备中",
    "trial_open": "试营业",
    "open": "营业中",
    "suspended": "暂停营业",
    "closed": "已停业",
}

# Forward-only lifecycle. A closed store is an archive, not a shortcut back
# into operations; reopening requires a new lifecycle decision.
STORE_TRANSITIONS = {
    "draft": frozenset({"preparing", "closed"}),
    "preparing": frozenset({"trial_open", "open", "closed"}),
    "trial_open": frozenset({"open", "suspended", "closed"}),
    "open": frozenset({"suspended", "closed"}),
    "suspended": frozenset({"open", "closed"}),
    "closed": frozenset(),
}

ACTIVE_ORDER_STATUSES = frozenset({
    "pending_payment", "paid", "confirmed", "checked_in", "in_service",
})
ACTIVE_OCCUPANCY_STATUSES = frozenset({
    "held", "waiting_service", "in_service", "post_service_present", "cleaning",
})


def require_store_open(store: Store | None, action: str = "到店服务") -> Store:
    """Reject new customer business when a store is not accepting orders.

    Existing orders are deliberately not touched here: a store suspension must
    stop new demand without invalidating service that is already in progress.
    """
    if store is None:
        raise HTTPException(status_code=404, detail="门店不存在")
    if store.status not in OPEN_STORE_STATUSES:
        label = STORE_STATUS_LABELS.get(store.status, store.status)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STORE_NOT_OPEN",
                "message": f"门店当前为「{label}」，暂不可{action}",
                "store_status": store.status,
            },
        )
    return store


def build_store_opening_check(db: Session, store: Store) -> dict:
    """Return the minimum operational readiness checklist for opening a store."""
    position_count = db.scalar(
        select(Room.id).where(
            Room.store_id == store.id,
            Room.is_service_position.is_(True),
            Room.is_space_container.is_(False),
            Room.operational_status == "active",
        ).limit(1)
    )
    project_count = db.scalar(
        select(Project.id).where(
            Project.store_id == store.id,
            Project.publication_status == "published",
        ).limit(1)
    )
    page_published = db.scalar(
        select(PageContent.id).where(
            PageContent.store_id == store.id,
            PageContent.page_key == "diy-home",
            PageContent.published.is_(True),
        ).limit(1)
    )
    checks = [
        {
            "key": "store_profile",
            "label": "门店资料",
            "passed": bool(store.name.strip() and store.address.strip() and store.business_hours.strip()),
            "detail": "名称、地址和营业时间必须完整",
        },
        {
            "key": "service_position",
            "label": "服务位",
            "passed": position_count is not None,
            "detail": "至少一个启用的实际服务位",
        },
        {
            "key": "published_project",
            "label": "已发布项目",
            "passed": project_count is not None,
            "detail": "至少一个已发布服务项目",
        },
        {
            "key": "published_page",
            "label": "顾客页面",
            "passed": page_published is not None,
            "detail": "首页内容必须已发布",
        },
    ]
    return {"ready": all(item["passed"] for item in checks), "checks": checks}


def enforce_store_opening_check(db: Session, store: Store) -> None:
    result = build_store_opening_check(db, store)
    if result["ready"]:
        return
    failed = [item for item in result["checks"] if not item["passed"]]
    raise HTTPException(
        status_code=409,
        detail={
            "code": "STORE_OPENING_CHECK_FAILED",
            "message": "门店尚未满足开业条件",
            "failed_checks": failed,
            "checks": result["checks"],
        },
    )


def validate_store_transition(current: str, target: str) -> None:
    """Enforce the documented store lifecycle transition graph."""
    if current == target:
        return
    allowed = STORE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        current_label = STORE_STATUS_LABELS.get(current, current)
        target_label = STORE_STATUS_LABELS.get(target, target)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_STORE_TRANSITION",
                "message": f"门店不能从「{current_label}」直接变为「{target_label}」",
                "current_status": current,
                "target_status": target,
                "allowed_statuses": sorted(allowed),
            },
        )


def validate_store_can_close(db: Session, store_id: int) -> None:
    """A store with live orders or active occupations cannot be archived."""
    active_orders = db.scalar(
        select(Order).where(
            Order.store_id == store_id,
            Order.status.in_(ACTIVE_ORDER_STATUSES),
        ).limit(1)
    )
    active_occupancies = db.scalar(
        select(PositionOccupancy).where(
            PositionOccupancy.store_id == store_id,
            PositionOccupancy.status.in_(ACTIVE_OCCUPANCY_STATUSES),
        ).limit(1)
    )
    if active_orders is not None or active_occupancies is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STORE_HAS_ACTIVE_BUSINESS",
                "message": "门店仍有未完成订单或进行中的服务位占用，不能停业",
                "active_order": active_orders is not None,
                "active_occupancy": active_occupancies is not None,
            },
        )
