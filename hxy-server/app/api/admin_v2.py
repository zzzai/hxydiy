"""管理后台 V2：房间/技师/项目/商品/标签/分层/自动化 — 完整 CRUD

权限：admin 可读写，staff 只读。所有写操作记录 AuditLog。
"""

from datetime import UTC, datetime, timezone
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select, func as sa_func, and_, or_, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, normalize_staff_role
from app.db.session import get_db
from app.models import (
    CouponTemplate, UserCoupon, MemberPlan, Recharge,
    Project, PriceBook, Addon, Product, Store, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, ServiceLine, PageContent,
    EventLog, Order, OrderEvent, User, AuditLog, Staff, PositionOccupancy,
    MembershipBenefitGrant, CustomerTrustedDevice, MembershipCode,
    CustomerProfileRecord,
    ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup,
    TechnicianInvite,
)
from app.domain.catalog_options import CatalogDomainError, copy_catalog_version_graph, lock_catalog_projects
from app.domain.occupancy import audit_occupancy, release_occupancy
from app.models.operations import Room, Technician
from app.models.room_assign import RoomAssignment
from app.models.service import ServiceAssignment, ServiceOrder, Visit
from app.models.scrm import (
    CustomerTag, CustomerTagRelation, CustomerSegment,
    AutomationRule, AutomationLog,
)
from app.schemas.profile import ProfileRecordCreate

router = APIRouter(prefix="/admin/v2", tags=["admin-v2"])


class TrustedDeviceRevokeIn(BaseModel):
    reason: str = Field(min_length=2, max_length=200)


@router.get("/users/{user_id}/trusted-device")
def get_customer_trusted_device(user_id: int, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db); _require_admin(staff); _require_store_user(db, user_id, staff)
    device = db.scalar(select(CustomerTrustedDevice).where(CustomerTrustedDevice.user_id == user_id, CustomerTrustedDevice.status == "active").order_by(CustomerTrustedDevice.created_at.desc()))
    return {"bound": bool(device), "created_at": device.created_at if device else None, "last_seen_at": device.last_seen_at if device else None}


@router.post("/users/{user_id}/trusted-device/revoke")
def revoke_customer_trusted_device(user_id: int, body: TrustedDeviceRevokeIn, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db); _require_admin(staff); user = _require_store_user(db, user_id, staff)
    now = datetime.now(timezone.utc)
    devices = list(db.scalars(select(CustomerTrustedDevice).where(CustomerTrustedDevice.user_id == user_id, CustomerTrustedDevice.status == "active")))
    for device in devices: device.status = "revoked"; device.revoked_at = now
    user.customer_login_version = int(user.customer_login_version or 1) + 1
    db.query(MembershipCode).filter(MembershipCode.user_id == user_id, MembershipCode.status.in_(["issued", "scanned_pending"])).update({"status": "revoked"}, synchronize_session=False)
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action="revoke_customer_trusted_device", entity_type="user", entity_id=str(user_id), detail={"reason": body.reason, "revoked_count": len(devices)}))
    db.commit()
    return {"revoked": bool(devices)}


# ─── helpers ─────────────────────────────────────────

def _require_admin(staff: Staff):
    try:
        normalized_role = normalize_staff_role(getattr(staff, "role", None), getattr(staff, "technician_id", None))
    except (AttributeError, ValueError, TypeError):
        # 登录层通常会先拦截旧/非法角色，但 endpoint helper 也必须独立保持
        # 结构化鉴权失败，避免测试 mock、内部调用或未来中间件绕过时冒泡成 500。
        normalized_role = None
    if normalized_role != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可操作"})


def _staff_store_id(staff: Staff) -> int:
    if not staff.store_id:
        raise HTTPException(status_code=403, detail="当前账号未绑定门店")
    return staff.store_id


def _scoped_store_id(staff: Staff, requested_store_id: int | None = None) -> int:
    store_id = _staff_store_id(staff)
    if requested_store_id is not None and requested_store_id != store_id:
        raise HTTPException(status_code=403, detail="无权访问其他门店数据")
    return store_id


def _require_headquarters_admin(staff: Staff) -> None:
    if staff.role != "admin" or staff.store_id is not None:
        raise HTTPException(status_code=403, detail={"code": "HEADQUARTERS_ADMIN_REQUIRED", "message": "仅未绑定门店的总部管理员可以维护门店主数据"})


def _is_headquarters_admin(staff: Staff) -> bool:
    """总部管理员是未绑定具体门店的 admin；绑定门店的 admin 仍是店长。"""
    # 使用 getattr 兼容少量旧测试/适配器传入的最小 staff 对象，缺少角色时按非总部处理。
    return getattr(staff, "role", None) == "admin" and getattr(staff, "store_id", None) is None


def _require_catalog_master_admin(staff: Staff) -> None:
    """目录/商品主数据只能由总部管理员维护。"""
    _require_headquarters_admin(staff)


def _require_catalog_write(
    staff: Staff,
    fields: set[str],
    *,
    publication_status: str | None = None,
    current_publication_status: str | None = None,
    store_allowed_publication_statuses: set[str] | None = None,
    allow_store_toggle: bool = True,
) -> None:
    """总部可完整写主数据；店长仅可修改本店 publication_status。"""
    if _is_headquarters_admin(staff):
        return
    try:
        normalized_role = normalize_staff_role(getattr(staff, "role", None), getattr(staff, "technician_id", None))
    except (AttributeError, TypeError, ValueError):
        normalized_role = None
    allowed_statuses = store_allowed_publication_statuses or {"published", "inactive"}
    if (allow_store_toggle and normalized_role == "manager" and staff.store_id is not None
            and fields == {"publication_status"} and publication_status in allowed_statuses
            and current_publication_status in {"draft", "candidate", "published", "inactive"}):
        return
    raise HTTPException(
        status_code=403,
        detail={"code": "HEADQUARTERS_ADMIN_REQUIRED", "message": "主数据仅总部管理员可维护，店长只能上下架本店内容"},
    )


def _reject_physical_resource_api() -> None:
    raise HTTPException(status_code=410, detail={"code": "DIY_PHYSICAL_RESOURCE_FORBIDDEN", "message": "DIY 管理端不提供物理资源派单操作"})


def _require_owned(entity, staff: Staff, not_found_detail: str):
    if not entity or entity.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail=not_found_detail)
    return entity


def _store_user_ids(store_id: int):
    """门店顾客：有本店订单/选单，或由本店开通会员的顾客。"""
    order_users = select(Order.user_id).where(Order.store_id == store_id)
    selection_users = select(SelectionSession.customer_id).where(
        SelectionSession.store_id == store_id,
        SelectionSession.customer_id.is_not(None),
    )
    member_users = select(User.id).where(
        User.is_member == True,
        User.membership_store_id == store_id,
    )
    return union(order_users, selection_users, member_users)


def _require_store_user(db: Session, user_id: int, staff: Staff) -> User:
    user = db.scalar(select(User).where(
        User.id == user_id,
        User.id.in_(_store_user_ids(_staff_store_id(staff))),
    ))
    if not user:
        raise HTTPException(status_code=404, detail="顾客不存在")
    return user


def _locked_store_user(db: Session, user_id: int, staff: Staff) -> User:
    user = db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.id.in_(_store_user_ids(_staff_store_id(staff))),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user:
        raise HTTPException(status_code=404, detail="顾客不存在")
    return user


def _audit(
    db: Session,
    actor: str | Staff,
    action: str,
    entity: str,
    eid: str,
    detail: dict = None,
    *,
    store_id: int | None = None,
):
    """写入带门店作用域的后台审计记录。

    新调用应传入 Staff 实例，这样门店归属不会依赖 detail JSON；保留字符串
    actor 兼容旧调用和系统脚本，并从 detail/实体标识中尽力读取历史作用域。
    """
    detail = detail or {}
    if isinstance(actor, Staff):
        actor_id = actor.name
        store_id = store_id if store_id is not None else actor.store_id
    else:
        actor_id = actor
        store_id = store_id if store_id is not None else detail.get("store_id")
    if store_id is None and entity == "store":
        try:
            store_id = int(str(eid).split(":", 1)[0])
        except (TypeError, ValueError):
            store_id = None
    db.add(AuditLog(
        actor_type="staff", actor_id=actor_id, store_id=store_id, action=action,
        entity_type=entity, entity_id=eid, detail=detail,
    ))


Paginated = dict  # { items, total, page, page_size }


TECHNICIAN_ACTIVE_SERVICE_STATUSES = {
    "draft", "waiting_assignment", "assigned", "ready", "in_service", "pending_checkout",
}
TECHNICIAN_HISTORY_SERVICE_STATUSES = {"completed", "cancelled"}
TECHNICIAN_REDACTED_ITEM_KEYS = {
    "amount", "amount_cents", "balance", "balance_cents", "cost", "discount",
    "member", "member_price", "member_price_cents", "pay_amount_cents", "phone",
    "price", "price_cents", "profile", "total", "total_amount_cents",
}


def _mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else "****"


def _redact_technician_item(value):
    if isinstance(value, dict):
        return {
            key: _redact_technician_item(item)
            for key, item in value.items()
            if key.lower() not in TECHNICIAN_REDACTED_ITEM_KEYS
            and not any(marker in key.lower() for marker in ("price", "amount", "member", "phone", "profile"))
        }
    if isinstance(value, list):
        return [_redact_technician_item(item) for item in value]
    return value


class StoreMasterIn(BaseModel):
    store_code: str
    name: str
    city: str = ""
    address: str
    phone: str = ""
    business_hours: str = ""
    status: Literal["preparing", "open", "closed"] = "preparing"


class StoreMasterPatch(BaseModel):
    name: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    business_hours: str | None = None
    status: Literal["preparing", "open", "closed"] | None = None


def _store_master_view(store: Store) -> dict:
    return {
        "id": store.id,
        "store_code": store.store_code,
        "name": store.name,
        "city": store.city,
        "address": store.address,
        "phone": store.phone,
        "business_hours": store.business_hours,
        "status": store.status,
        "created_at": store.created_at.isoformat() if store.created_at else None,
        "updated_at": store.updated_at.isoformat() if store.updated_at else None,
    }


@router.get("/stores")
def list_store_master_data(
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = Query(None, max_length=64),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    _require_headquarters_admin(staff)
    query = select(Store)
    if keyword and keyword.strip():
        term = f"%{keyword.strip()}%"
        query = query.where(or_(Store.name.ilike(term), Store.store_code.ilike(term), Store.city.ilike(term)))
    total = db.scalar(select(sa_func.count()).select_from(query.subquery())) or 0
    items = db.execute(query.order_by(Store.id).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": [_store_master_view(store) for store in items], "total": total, "page": page, "page_size": page_size}


@router.post("/stores")
def create_store_master_data(
    body: StoreMasterIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_headquarters_admin(staff)
    if db.scalar(select(Store).where(Store.store_code == body.store_code)):
        raise HTTPException(status_code=400, detail="门店编码已存在")
    store = Store(**body.model_dump())
    db.add(store)
    db.flush()
    _audit(db, staff, "create_store", "store", str(store.id), {"store_code": store.store_code})
    db.commit()
    db.refresh(store)
    return _store_master_view(store)


@router.patch("/stores/{store_id}")
def update_store_master_data(
    store_id: int,
    body: StoreMasterPatch,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_headquarters_admin(staff)
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(store, field, value)
    _audit(db, staff, "update_store", "store", str(store.id), changes)
    db.commit()
    db.refresh(store)
    return _store_master_view(store)


def _customer_display_name(user: User) -> str:
    if user.nickname:
        return user.nickname
    if user.openid.startswith("anon_"):
        return f"匿名访客#{user.openid[-6:].upper()}"
    return f"用户{user.id}"


def _masked_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else phone


class PageContentIn(BaseModel):
    title: str = "到店服务选单"
    subtitle: str = "按需要，自由搭配"
    promo_banners: list = []
    tea_options: list = []
    coupon_prompt: dict = {}
    brand_story: dict = {}
    published: bool = False


class SelectionChangeRejectIn(BaseModel):
    reason: str = ""


def _page_content_view(content: PageContent) -> dict:
    return {key: getattr(content, key) for key in (
        "id", "store_id", "page_key", "title", "subtitle", "promo_banners",
        "tea_options", "coupon_prompt", "brand_story", "published", "updated_at",
    )}


@router.get("/page-content")
def get_page_content_admin(page_key: str = Query("diy-home"), db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    content = db.scalar(select(PageContent).where(PageContent.store_id == store_id, PageContent.page_key == page_key))
    if not content:
        content = PageContent(store_id=store_id, page_key=page_key)
        db.add(content)
        db.commit()
        db.refresh(content)
    return _page_content_view(content)


@router.put("/page-content")
def update_page_content(page_key: str = Query("diy-home"), body: PageContentIn = ..., db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    content = db.scalar(select(PageContent).where(PageContent.store_id == store_id, PageContent.page_key == page_key))
    if not content:
        content = PageContent(store_id=store_id, page_key=page_key)
        db.add(content)
    for key, value in body.model_dump().items():
        setattr(content, key, value)
    _audit(db, staff, "update_page_content", "page_content", f"{store_id}:{page_key}", {"store_id": store_id})
    db.commit()
    db.refresh(content)
    return _page_content_view(content)

# ──────────────────────────────────────────────────────
# 0. 到店服务选单：独立于订单的顾客 DIY 需求
# ──────────────────────────────────────────────────────

def _selection_view(session: SelectionSession, customer: User | None = None, feedback: ServiceFeedback | None = None) -> dict:
    return {
        "id": session.id,
        "store_id": session.store_id,
        "source": session.source,
        "device_label": session.device_label,
        "status": session.status,
        "customer_id": session.customer_id,
        "fulfillment_order_id": session.fulfillment_order_id,
        "customer": ({
            "id": customer.id,
            "nickname": _customer_display_name(customer),
            "phone": _masked_phone(customer.phone),
            "is_member": customer.is_member,
            "member_type": customer.member_type,
            "member_expire_at": customer.member_expire_at.isoformat() if customer.member_expire_at else None,
        } if customer else None),
        "feedback": ({
            "id": feedback.id,
            "rating": feedback.rating,
            "tags": feedback.tags or [],
            "note": feedback.note,
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        } if feedback else None),
        "items": session.items or [],
        "diy_preferences": session.diy_preferences or {},
        "pricing_snapshot": session.pricing_snapshot or {},
        "store_total_cents": session.store_total_cents,
        "member_total_cents": session.member_total_cents,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        "confirmed_at": session.confirmed_at.isoformat() if session.confirmed_at else None,
        "cancelled_at": session.cancelled_at.isoformat() if session.cancelled_at else None,
    }


class FeedbackFollowUpIn(BaseModel):
    follow_up_status: Literal["open", "in_progress", "resolved", "dismissed"]
    follow_up_note: str = ""


@router.get("/feedback")
def list_feedback(
    low_rating_only: bool = Query(False),
    follow_up_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    query = select(ServiceFeedback).where(ServiceFeedback.store_id == store_id)
    if low_rating_only:
        query = query.where(ServiceFeedback.rating <= 2)
    if follow_up_status:
        query = query.where(ServiceFeedback.follow_up_status == follow_up_status)
    query = query.order_by(ServiceFeedback.created_at.desc(), ServiceFeedback.id.desc())
    total = db.scalar(select(sa_func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
    return {
        "items": [{
            "id": row.id,
            "store_id": row.store_id,
            "selection_session_id": row.selection_session_id,
            "customer_id": row.customer_id,
            "rating": row.rating,
            "tags": row.tags or [],
            "note": row.note,
            "follow_up_status": row.follow_up_status,
            "follow_up_staff_id": row.follow_up_staff_id,
            "follow_up_note": row.follow_up_note,
            "followed_up_at": row.followed_up_at.isoformat() if row.followed_up_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/feedback/{feedback_id}")
def update_feedback_follow_up(
    feedback_id: int,
    body: FeedbackFollowUpIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> dict:
    staff = _current_staff(authorization, db)
    feedback = db.get(ServiceFeedback, feedback_id)
    if not feedback or feedback.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="评价不存在")
    feedback.follow_up_status = body.follow_up_status
    feedback.follow_up_note = body.follow_up_note.strip()[:1000]
    feedback.follow_up_staff_id = staff.id
    feedback.followed_up_at = datetime.now(timezone.utc)
    _audit(db, staff, "update_feedback_follow_up", "service_feedback", str(feedback.id), {
        "store_id": feedback.store_id,
        "follow_up_status": feedback.follow_up_status,
    })
    db.commit()
    return {
        "id": feedback.id,
        "follow_up_status": feedback.follow_up_status,
        "follow_up_staff_id": feedback.follow_up_staff_id,
        "follow_up_note": feedback.follow_up_note,
        "followed_up_at": feedback.followed_up_at.isoformat() if feedback.followed_up_at else None,
    }


@router.get("/selection-sessions")
def list_selection_sessions(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    q = select(SelectionSession).where(SelectionSession.store_id == store_id)
    if status:
        q = q.where(SelectionSession.status == status)
    q = q.order_by(SelectionSession.created_at.desc())
    total = db.scalar(select(sa_func.count()).select_from(q.subquery())) or 0
    rows = db.execute(
        select(SelectionSession, User, ServiceFeedback)
        .outerjoin(User, User.id == SelectionSession.customer_id)
        .outerjoin(ServiceFeedback, ServiceFeedback.selection_session_id == SelectionSession.id)
        .where(SelectionSession.id.in_(select(q.subquery().c.id)))
        .order_by(SelectionSession.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_selection_view(session, customer, feedback) for session, customer, feedback in rows], "total": total, "page": page, "page_size": page_size}


def _owned_selection(db: Session, session_id: str, staff: Staff) -> SelectionSession:
    session = db.get(SelectionSession, session_id)
    if not session or session.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="选单不存在")
    return session


def _locked_owned_selection(db: Session, session_id: str, staff: Staff) -> SelectionSession:
    session = db.scalar(
        select(SelectionSession)
        .where(SelectionSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not session or session.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="选单不存在")
    return session


def _sync_unsettled_fulfillment_bill(
    db: Session,
    session: SelectionSession,
    pricing: dict,
) -> None:
    """把已转服务单但尚未收款的账单更新为本次确认冻结快照。"""
    if not session.fulfillment_order_id:
        return
    order = db.scalar(
        select(Order)
        .where(Order.id == session.fulfillment_order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not order or order.store_id != session.store_id:
        raise HTTPException(status_code=409, detail={
            "code": "FULFILLMENT_BILL_UNAVAILABLE",
            "message": "关联服务账单不存在或不属于当前门店",
        })
    service_order = db.scalar(
        select(ServiceOrder)
        .where(
            ServiceOrder.order_id == order.id,
            ServiceOrder.store_id == session.store_id,
        )
        .order_by(ServiceOrder.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not service_order:
        raise HTTPException(status_code=409, detail={
            "code": "FULFILLMENT_BILL_UNAVAILABLE",
            "message": "关联服务单不存在",
        })
    if (
        order.pay_status != "unpaid"
        or service_order.settled_at is not None
        or service_order.status == "completed"
    ):
        raise HTTPException(status_code=409, detail={
            "code": "FULFILLMENT_BILL_NOT_SYNCABLE",
            "message": "已收款或已结算的服务单不能追加确认项目",
        })
    pricing_lines = pricing.get("lines")
    if not isinstance(pricing_lines, list) or not all(isinstance(line, dict) for line in pricing_lines):
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_PRICING_INVALID",
            "message": "确认冻结报价缺少服务账单项目",
        })
    frozen_items = [dict(line) for line in pricing_lines]
    payable_total = int(pricing.get("payable_total_cents", 0))
    store_total = int(pricing.get("store_total_cents", payable_total))
    order.items = frozen_items
    order.total_amount_cents = payable_total
    order.discount_cents = max(0, store_total - payable_total)
    order.member_discount_cents = max(
        0,
        store_total - int(pricing.get("member_total_cents", payable_total) or payable_total),
    )
    order.pay_amount_cents = payable_total
    service_order.items = frozen_items
    service_order.total_amount_cents = payable_total


def _selection_change_request_view(
    change: SelectionChangeRequest,
    session: SelectionSession,
    revision: SelectionRevision,
) -> dict:
    snapshot = revision.snapshot or {}
    return {
        "id": change.id,
        "state": change.state,
        "reason": change.reason,
        "created_at": change.created_at.isoformat() if change.created_at else None,
        "selection": {
            "id": session.id,
            "source": session.source,
            "device_label": session.device_label,
            "status": session.status,
        },
        "revision": {
            "id": revision.id,
            "revision_no": revision.revision_no,
            "added_items": snapshot.get("added_items", []),
            "pricing": snapshot.get("pricing", {}),
        },
    }


@router.get("/selection-change-requests")
def list_selection_change_requests(
    state: str = Query("awaiting_staff_confirmation"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    query = (
        select(SelectionChangeRequest, SelectionSession, SelectionRevision)
        .join(SelectionSession, SelectionSession.id == SelectionChangeRequest.selection_session_id)
        .join(SelectionRevision, SelectionRevision.id == SelectionChangeRequest.selection_revision_id)
        .where(SelectionSession.store_id == store_id)
        .order_by(SelectionChangeRequest.created_at.asc())
    )
    if state:
        query = query.where(SelectionChangeRequest.state == state)
    rows = db.execute(query).all()
    return {
        "items": [_selection_change_request_view(change, session, revision) for change, session, revision in rows],
        "total": len(rows),
    }


@router.post("/selection-sessions/{session_id}/confirm")
def confirm_selection_session(session_id: str, db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    session = _locked_owned_selection(db, session_id, staff)
    if session.status == "confirmed":
        return _selection_view(session, db.get(User, session.customer_id) if session.customer_id else None)
    if session.status != "submitted":
        raise HTTPException(status_code=409, detail="只有已提交选单可以确认")
    submitted_revisions = list(db.scalars(
        select(SelectionRevision)
        .where(
            SelectionRevision.selection_session_id == session.id,
            SelectionRevision.state == "submitted",
        )
        .order_by(SelectionRevision.revision_no.desc(), SelectionRevision.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    revision = submitted_revisions[0] if submitted_revisions else None
    confirmed_at = datetime.now(timezone.utc)
    if revision is None:
        latest_revision_no = db.scalar(select(sa_func.max(SelectionRevision.revision_no)).where(
            SelectionRevision.selection_session_id == session.id,
        )) or 0
        revision = SelectionRevision(
            id=str(uuid.uuid4()),
            selection_session_id=session.id,
            revision_no=latest_revision_no + 1,
            state="submitted",
            idempotency_key=f"legacy-submit-confirm:{session.id}",
            snapshot={
                "items": list(session.items or []),
                "pricing": dict(session.pricing_snapshot or {}),
                "diy_preferences": dict(session.diy_preferences or {}),
            },
        )
        db.add(revision)
        db.flush()
    else:
        for superseded in submitted_revisions[1:]:
            superseded.state = "superseded"
    occupancy = db.scalar(
        select(PositionOccupancy)
        .where(PositionOccupancy.selection_session_id == session.id)
        .order_by(PositionOccupancy.id.desc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if occupancy and occupancy.status in {"post_service_present", "cleaning", "released"}:
        raise HTTPException(status_code=409, detail="服务已结束，当前选单不能确认")
    confirmed_items = []
    for item in (revision.snapshot or {}).get("items", []):
        service_line_id = str(uuid.uuid4())
        confirmed_item = {
            **item,
            "service_line_id": service_line_id,
            "state": "confirmed",
        }
        db.add(ServiceLine(
            id=service_line_id,
            selection_session_id=session.id,
            selection_revision_id=revision.id,
            snapshot=confirmed_item,
            state="pending",
        ))
        confirmed_items.append(confirmed_item)
    revision.state = "confirmed"
    revision.confirmed_at = confirmed_at
    revision.confirmed_by_staff_id = staff.id

    # 泡脚组合优惠只取前台确认的独立服务单位；确认后立即刷新冻结报价。
    session.items = confirmed_items
    from app.api.selections import refresh_session_pricing
    try:
        pricing = refresh_session_pricing(db, session, confirmed_at=confirmed_at)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_PRICING_INVALID",
            "message": str(exc),
        }) from exc
    revision.snapshot = {
        **(revision.snapshot or {}),
        "items": confirmed_items,
        "pricing": pricing,
    }
    session.status = "confirmed"
    session.confirmed_at = confirmed_at
    _audit(db, staff, "confirm_selection", "selection_session", session.id)
    db.commit()
    db.refresh(session)
    return _selection_view(session, db.get(User, session.customer_id) if session.customer_id else None)


@router.post("/selection-sessions/{session_id}/cancel")
def cancel_selection_session(session_id: str, db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    session = _owned_selection(db, session_id, staff)
    if session.status == "cancelled":
        return _selection_view(session, db.get(User, session.customer_id) if session.customer_id else None)
    if session.status not in {"submitted", "confirmed"}:
        raise HTTPException(status_code=409, detail="当前选单不能取消")
    session.status = "cancelled"
    session.cancelled_at = datetime.now(timezone.utc)
    occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_session_id == session.id,
    ))
    if occupancy and occupancy.status in {"held", "waiting_service"}:
        before = occupancy.status
        release_occupancy(occupancy, "选单已取消", now=session.cancelled_at)
        audit_occupancy(db, occupancy, "selection_cancelled", "staff", str(staff.id), {
            "from_status": before,
            "to_status": occupancy.status,
            "selection_session_id": session.id,
        })
    _audit(db, staff, "cancel_selection", "selection_session", session.id)
    db.commit()
    db.refresh(session)
    return _selection_view(session, db.get(User, session.customer_id) if session.customer_id else None)


@router.post("/selection-change-requests/{request_id}/approve")
def approve_selection_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    change_ref = db.get(SelectionChangeRequest, request_id)
    if not change_ref:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    session = _locked_owned_selection(db, change_ref.selection_session_id, staff)
    change = db.scalar(
        select(SelectionChangeRequest)
        .where(SelectionChangeRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not change or change.selection_session_id != session.id:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    revision = db.scalar(
        select(SelectionRevision)
        .where(SelectionRevision.id == change.selection_revision_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not revision or revision.selection_session_id != session.id:
        raise HTTPException(status_code=409, detail="加选版本不存在")
    if change.state == "approved":
        lines = list(db.scalars(
            select(ServiceLine)
            .where(ServiceLine.selection_revision_id == change.selection_revision_id)
            .order_by(ServiceLine.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        ))
        return {"id": change.id, "state": change.state, "service_lines": [_service_line_view(line) for line in lines]}
    if change.state != "awaiting_staff_confirmation":
        raise HTTPException(status_code=409, detail="当前加选请求不能确认")
    if session.status != "confirmed":
        raise HTTPException(status_code=409, detail="当前选单状态不能确认加选")
    earliest_pending_revision_no = db.scalar(
        select(sa_func.min(SelectionRevision.revision_no))
        .join(
            SelectionChangeRequest,
            SelectionChangeRequest.selection_revision_id == SelectionRevision.id,
        )
        .where(
            SelectionChangeRequest.selection_session_id == session.id,
            SelectionChangeRequest.state == "awaiting_staff_confirmation",
        )
    )
    if earliest_pending_revision_no != revision.revision_no:
        raise HTTPException(status_code=409, detail={
            "code": "SELECTION_REVISION_OUT_OF_ORDER",
            "message": "请先处理更早提交的加选版本",
        })
    occupancy = db.scalar(
        select(PositionOccupancy)
        .where(PositionOccupancy.selection_session_id == session.id)
        .order_by(PositionOccupancy.id.desc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not occupancy or occupancy.status != "in_service":
        raise HTTPException(status_code=409, detail="服务已结束，当前加选不能确认")
    approved_at = datetime.now(timezone.utc)
    snapshot = revision.snapshot or {}
    lines = []
    confirmed_added_items = []
    for item in snapshot.get("added_items", []):
        service_line_id = str(uuid.uuid4())
        confirmed_item = {
            **item,
            "service_line_id": service_line_id,
            "state": "confirmed",
        }
        line = ServiceLine(
            id=service_line_id,
            selection_session_id=session.id,
            selection_revision_id=revision.id,
            snapshot=confirmed_item,
            state="pending",
        )
        db.add(line)
        lines.append(line)
        confirmed_added_items.append(confirmed_item)
    confirmed_items = [*(session.items or []), *confirmed_added_items]
    session.items = confirmed_items
    session.diy_preferences = snapshot.get("diy_preferences", session.diy_preferences or {})
    from app.api.selections import refresh_session_pricing
    try:
        pricing = refresh_session_pricing(db, session, confirmed_at=approved_at)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_PRICING_INVALID",
            "message": str(exc),
        }) from exc
    revision.snapshot = {
        **snapshot,
        "items": confirmed_items,
        "added_items": confirmed_added_items,
        "pricing": pricing,
    }
    _sync_unsettled_fulfillment_bill(db, session, pricing)
    session.status = "confirmed"
    session.confirmed_at = session.confirmed_at or approved_at
    change.state = "approved"
    change.resolved_at = approved_at
    change.resolved_by_staff_id = staff.id
    revision.state = "confirmed"
    revision.confirmed_at = approved_at
    revision.confirmed_by_staff_id = staff.id
    _audit(db, staff, "approve_selection_change", "selection_change_request", change.id, {
        "selection_session_id": session.id,
        "service_line_count": len(lines),
    })
    db.commit()
    return {"id": change.id, "state": change.state, "service_lines": [_service_line_view(line) for line in lines]}


@router.post("/selection-change-requests/{request_id}/reject")
def reject_selection_change_request(
    request_id: str,
    body: SelectionChangeRejectIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    change_ref = db.get(SelectionChangeRequest, request_id)
    if not change_ref:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    session = _locked_owned_selection(db, change_ref.selection_session_id, staff)
    change = db.scalar(
        select(SelectionChangeRequest)
        .where(SelectionChangeRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not change or change.selection_session_id != session.id:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="拒绝加选必须填写原因")
    if change.state == "rejected":
        return {"id": change.id, "state": change.state, "reason": change.reason}
    if change.state != "awaiting_staff_confirmation":
        raise HTTPException(status_code=409, detail="当前加选请求不能拒绝")
    revision = db.scalar(
        select(SelectionRevision)
        .where(SelectionRevision.id == change.selection_revision_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not revision or revision.selection_session_id != session.id:
        raise HTTPException(status_code=409, detail="加选版本不存在")
    change.state = "rejected"
    change.reason = reason
    change.resolved_at = datetime.now(timezone.utc)
    change.resolved_by_staff_id = staff.id
    revision.state = "rejected"
    _audit(db, staff, "reject_selection_change", "selection_change_request", change.id, {
        "selection_session_id": session.id,
        "reason": reason,
    })
    db.commit()
    return {"id": change.id, "state": change.state, "reason": change.reason}


def _service_line_view(line: ServiceLine) -> dict:
    return {
        "id": line.id,
        "selection_session_id": line.selection_session_id,
        "selection_revision_id": line.selection_revision_id,
        "snapshot": line.snapshot or {},
        "state": line.state,
    }

# ──────────────────────────────────────────────────────
# 1. 房间管理
# ──────────────────────────────────────────────────────

class RoomIn(BaseModel):
    store_id: int
    code: str
    name: str
    room_type: str = "room"
    floor: str = ""
    capacity: int = 1
    room_group: str = "sofa"
    status: str = "available"
    note: str = ""
    sort_order: int = 0
    parent_room_id: int | None = None
    is_space_container: bool = False
    is_service_position: bool | None = None


@router.get("/rooms")
def list_rooms(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    scoped_store_id = _scoped_store_id(staff, store_id)
    q = select(Room).where(Room.store_id == scoped_store_id)
    if status:
        q = q.where(Room.status == status)
    q = q.order_by(Room.sort_order, Room.id)
    total = db.scalar(select(sa_func.count()).select_from(q.subquery()))
    items = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    bed_counts = dict(db.execute(
        select(Room.parent_room_id, sa_func.count(Room.id))
        .where(Room.parent_room_id.is_not(None), Room.room_type == "bed")
        .group_by(Room.parent_room_id)
    ).all())
    return {"items": [{
        "id": r.id, "store_id": r.store_id, "code": r.code, "name": r.name,
        "room_type": r.room_type, "floor": r.floor, "capacity": r.capacity,
        "room_group": r.room_group, "used_count": r.used_count,
        "current_tech": r.current_tech,
        "status": r.status, "note": r.note, "sort_order": r.sort_order,
        "operational_status": r.operational_status,
        "parent_room_id": r.parent_room_id,
        "is_space_container": r.is_space_container,
        "is_service_position": r.is_service_position,
        "bed_count": bed_counts.get(r.id, 0),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in items], "total": total, "page": page, "page_size": page_size}


@router.post("/rooms")
def create_room(body: RoomIn, db: Session = Depends(get_db),
                authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    _scoped_store_id(s, body.store_id)
    if db.scalar(select(Room).where(Room.code == body.code)):
        raise HTTPException(400, "编码已存在")
    payload = body.model_dump()
    if body.is_space_container:
        payload["is_service_position"] = False
        payload["customer_selectable"] = False
    elif body.is_service_position is None:
        payload["is_service_position"] = True
    if body.parent_room_id is not None:
        parent = _require_owned(db.get(Room, body.parent_room_id), s, "所属房间不存在")
        if not parent.is_space_container:
            raise HTTPException(400, "床位只能归属房间空间容器")
        if body.room_type != "bed":
            raise HTTPException(400, "只有床位可以归属房间空间容器")
    r = Room(**payload)
    db.add(r)
    _audit(db, s, "create_room", "room", body.code)
    db.commit()
    return {"id": r.id, "code": r.code}


@router.post("/rooms/{room_id}")
def update_room(room_id: int, body: dict, db: Session = Depends(get_db),
                authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = _require_owned(db.get(Room, room_id), s, "房间不存在")
    if r.is_space_container:
        child_count = db.scalar(select(sa_func.count(Room.id)).where(Room.parent_room_id == r.id)) or 0
        if child_count:
            raise HTTPException(409, "请先移除房间内的床位，再删除房间")
    active_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == r.id,
    ))
    if active_occupancy:
        raise HTTPException(409, "当前服务位已有活动占用，请在服务位看板完成现场操作")
    runtime_fields = {"status", "used_count", "current_tech", "version"}
    if runtime_fields.intersection(body):
        raise HTTPException(400, "房态和服务信息请使用房态操作或服务位看板更新")
    if "parent_room_id" in body:
        parent_id = body["parent_room_id"]
        if parent_id is not None:
            parent = _require_owned(db.get(Room, parent_id), s, "所属房间不存在")
            if not parent.is_space_container or r.room_type != "bed":
                raise HTTPException(400, "床位只能归属房间空间容器")
        if r.is_space_container and parent_id is not None:
            raise HTTPException(400, "空间容器不能归属其他房间")
    if body.get("is_space_container") is True:
        body["is_service_position"] = False
        body["customer_selectable"] = False
    for k, v in body.items():
        if hasattr(r, k) and k not in {"id", "store_id", *runtime_fields}:
            setattr(r, k, v)
    _audit(db, s, "update_room", "room", str(room_id))
    db.commit()
    return {"ok": True}


@router.delete("/rooms/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db),
                authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = _require_owned(db.get(Room, room_id), s, "房间不存在")
    active_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == r.id,
    ))
    if active_occupancy:
        raise HTTPException(409, "当前服务位已有活动占用，请在服务位看板完成现场操作")
    db.delete(r)
    _audit(db, s, "delete_room", "room", str(room_id))
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 2. 技师管理
# ──────────────────────────────────────────────────────

class TechIn(BaseModel):
    store_id: int
    code: str
    name: str
    phone: str = ""
    avatar_url: str = ""
    gender: str = ""
    level: str = "初级"
    skills: list = []
    intro: str = ""
    commission_rules: dict = {}
    default_commission_rate: float = 0.3
    status: str = "available"
    sort_order: int = 0


@router.get("/technicians")
def list_technicians(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    level: str | None = Query(None),
    page: int = 1, page_size: int = 50,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    scoped_store_id = _scoped_store_id(staff, store_id)
    q = select(Technician).where(Technician.store_id == scoped_store_id)
    if status:
        q = q.where(Technician.status == status)
    if level:
        q = q.where(Technician.level == level)
    q = q.order_by(Technician.sort_order, Technician.id)
    total = db.scalar(select(sa_func.count()).select_from(q.subquery()))
    items = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    staff_rows = db.scalars(select(Staff).where(Staff.store_id == scoped_store_id)).all()
    staff_by_technician = {row.technician_id: row for row in staff_rows if row.technician_id is not None}
    invite_rows = db.scalars(select(TechnicianInvite).where(TechnicianInvite.store_id == scoped_store_id)).all()
    invite_by_technician = {row.technician_id: row for row in invite_rows}
    result = []
    for t in items:
        staff = staff_by_technician.get(t.id)
        invite = invite_by_technician.get(t.id)
        if not staff:
            login_status = "not_opened"
        elif staff.status == "active":
            login_status = "active"
        elif staff.status == "disabled":
            login_status = "disabled" if t.status != "resigned" else "resigned"
        else:
            login_status = "invited" if invite and invite.used_at is None else "not_opened"
        result.append({
            "id": t.id, "store_id": t.store_id, "code": t.code, "name": t.name,
            "phone": t.phone, "avatar_url": t.avatar_url, "gender": t.gender,
            "level": t.level, "skills": t.skills, "intro": t.intro,
            "commission_rules": t.commission_rules,
            "default_commission_rate": t.default_commission_rate,
            "status": t.status, "sort_order": t.sort_order,
            "hire_date": t.hire_date.isoformat() if t.hire_date else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "username": staff.username if staff else None,
            "login_status": login_status,
            "credentials_version": staff.credentials_version if staff else None,
            "invite_expires_at": invite.expires_at.isoformat() if invite and invite.used_at is None else None,
        })
    return {"items": result, "total": total, "page": page, "page_size": page_size}


@router.post("/technicians")
def create_technician(body: TechIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    _scoped_store_id(s, body.store_id)
    if db.scalar(select(Technician).where(Technician.code == body.code)):
        raise HTTPException(400, "编码已存在")
    t = Technician(**body.model_dump())
    db.add(t)
    _audit(db, s, "create_tech", "technician", body.code)
    db.commit()
    return {"id": t.id, "code": t.code}


@router.post("/technicians/{tech_id}")
def update_technician(tech_id: int, body: dict, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    t = _require_owned(db.get(Technician, tech_id), s, "技师不存在")
    for k, v in body.items():
        if hasattr(t, k) and k not in {"id", "store_id"}:
            setattr(t, k, v)
    _audit(db, s, "update_tech", "technician", str(tech_id))
    db.commit()
    return {"ok": True}


@router.delete("/technicians/{tech_id}")
def delete_technician(tech_id: int, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    _require_owned(db.get(Technician, tech_id), s, "技师不存在")
    raise HTTPException(
        status_code=410,
        detail={
            "code": "TECHNICIAN_PHYSICAL_DELETE_FORBIDDEN",
            "message": "技师档案不可物理删除，请使用停用或办理离职",
        },
    )


# ──────────────────────────────────────────────────────
# 3. 项目管理（管理端 CRUD + 价格表同步）
# ──────────────────────────────────────────────────────

@router.get("/projects")
def list_projects_admin(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    category: str | None = Query(None),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    # FastAPI 注入时这些参数是原始值；部分契约测试会直接调用路由函数，
    # 此时默认值仍是 Query 对象，需要先还原为 None/实际默认值。
    if not isinstance(page, (int, type(None))):
        page = getattr(page, "default", None)
    if not isinstance(page_size, (int, type(None))):
        page_size = getattr(page_size, "default", None)
    staff = _current_staff(authorization, db)
    q = select(Project)
    if not _is_headquarters_admin(staff):
        scoped_store_id = _scoped_store_id(staff, store_id)
        q = q.where(Project.store_id == scoped_store_id)
    elif store_id is not None:
        q = q.where(Project.store_id == store_id)
    if status:
        q = q.where(Project.publication_status == status)
    if category:
        q = q.where(Project.category == category)
    if page is None and page_size is None:
        q = q.order_by(Project.id)
        projects = db.execute(q).scalars().all()
        total = None
        resolved_page = None
        resolved_page_size = None
    else:
        resolved_page = page or 1
        resolved_page_size = page_size or 50
        total = db.scalar(select(sa_func.count()).select_from(q.subquery())) or 0
        projects = db.execute(
            q.order_by(Project.id).offset((resolved_page - 1) * resolved_page_size).limit(resolved_page_size),
        ).scalars().all()
    result = []
    for p in projects:
        prices = db.execute(
            select(PriceBook)
            .where(
                PriceBook.project_id == p.id,
                or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > datetime.now(UTC)),
            )
            .order_by(PriceBook.price_type, PriceBook.published_at.desc(), PriceBook.id.desc())
        ).scalars().all()
        price_map = {}
        for pb in prices:
            price_map.setdefault(pb.price_type, pb.amount_cents)
        result.append({
            "id": p.id, "store_id": p.store_id, "code": p.code,
            "category": p.category, "category_mark": p.category_mark,
            "name": p.name, "duration_min": p.duration_min,
            "summary": p.summary, "image_url": p.image_url,
            "tags": p.tags, "detail_modules": p.detail_modules,
            "diy_options": p.diy_options, "display_order": p.display_order,
            "price_label": p.price_label,
            "publication_status": p.publication_status,
            "prices": price_map,  # {"store": 8900, "member": 6900, "group": 2990}
        })
    if total is None:
        return result
    return {"items": result, "total": total, "page": resolved_page, "page_size": resolved_page_size}


ProjectPriceType = Literal["store", "group", "member"]
ProjectPublicationStatus = Literal["draft", "candidate", "published", "inactive", "archived"]


class _StrictProjectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("code", "name", "category", check_fields=False)
    @classmethod
    def _required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("prices", check_fields=False)
    @classmethod
    def _prices_are_non_negative(cls, value: dict[ProjectPriceType, int] | None):
        if value is not None and any(amount < 0 for amount in value.values()):
            raise ValueError("price amounts must be non-negative")
        return value


class ProjectCreate(_StrictProjectModel):
    store_id: StrictInt
    code: StrictStr = Field(min_length=1, max_length=32)
    category: StrictStr = Field(default="bath", min_length=1, max_length=32)
    category_mark: StrictStr = Field(default="", max_length=8)
    name: StrictStr = Field(min_length=1, max_length=64)
    duration_min: StrictInt | None = Field(default=None, ge=0)
    summary: StrictStr = Field(default="", max_length=512)
    image_url: StrictStr = Field(default="", max_length=512)
    tags: list = Field(default_factory=list)
    detail_modules: list = Field(default_factory=list)
    # 保留历史 DIY 选项字段，管理端编辑器仍会维护该兼容结构。
    diy_options: list = Field(default_factory=list)
    display_order: StrictInt = Field(default=0, ge=0)
    price_label: StrictStr = Field(default="", max_length=32)
    publication_status: ProjectPublicationStatus = "draft"
    prices: dict[ProjectPriceType, StrictInt] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _published_project_requires_store_price(self):
        if self.publication_status == "published" and "store" not in self.prices:
            raise ValueError("published project requires a store price")
        return self


class ProjectPatch(_StrictProjectModel):
    code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    category: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    category_mark: StrictStr | None = Field(default=None, max_length=8)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    duration_min: StrictInt | None = Field(default=None, ge=0)
    summary: StrictStr | None = Field(default=None, max_length=512)
    image_url: StrictStr | None = Field(default=None, max_length=512)
    tags: list | None = None
    detail_modules: list | None = None
    diy_options: list | None = None
    display_order: StrictInt | None = Field(default=None, ge=0)
    price_label: StrictStr | None = Field(default=None, max_length=32)
    publication_status: ProjectPublicationStatus | None = None
    prices: dict[ProjectPriceType, StrictInt] | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_nulls(cls, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if item is None:
                    raise ValueError(f"{key} must not be null")
        return value


class ProjectDuplicateIn(_StrictProjectModel):
    code: StrictStr = Field(min_length=1, max_length=32)
    name: StrictStr = Field(min_length=1, max_length=64)


def _published_catalog_referrer_ids(db: Session, target_project_id: int) -> list[int]:
    return list(db.scalars(
        select(ProjectCatalogVersion.project_id)
        .join(ProjectOptionGroup, ProjectOptionGroup.catalog_version_id == ProjectCatalogVersion.id)
        .join(ProjectOptionChoice, ProjectOptionChoice.option_group_id == ProjectOptionGroup.id)
        .where(
            ProjectCatalogVersion.status == "published",
            ProjectOptionChoice.linked_project_id == target_project_id,
        )
        .order_by(ProjectCatalogVersion.project_id)
    ))


def _locked_project_for_update(db: Session, project_id: int, staff: Staff) -> tuple[Project, list[int]]:
    # 首次只读取引用方 ID；随后以全局升序一次拿到相关 Project 锁，再重新读取反向引用。
    preliminary = _published_catalog_referrer_ids(db, project_id)
    projects = lock_catalog_projects(db, [project_id, *preliminary])
    project = projects.get(project_id)
    if project is None or (not _is_headquarters_admin(staff) and project.store_id != _staff_store_id(staff)):
        raise HTTPException(status_code=404, detail="项目不存在")
    referrers = _published_catalog_referrer_ids(db, project_id)
    return project, referrers


def _append_project_prices(db: Session, project_id: int, prices: dict[ProjectPriceType, int], publisher: str) -> None:
    now = datetime.now(UTC)
    for price_type, amount_cents in prices.items():
        for current in db.scalars(
            select(PriceBook).where(
                PriceBook.project_id == project_id,
                PriceBook.price_type == price_type,
                or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now),
            )
        ):
            current.effective_to = now
        db.add(PriceBook(
            project_id=project_id,
            price_type=price_type,
            amount_cents=amount_cents,
            publisher=publisher,
            published_at=now,
        ))


def _has_project_store_price(
    db: Session,
    project_id: int,
    pending_prices: dict[ProjectPriceType, int] | None = None,
) -> bool:
    if pending_prices is not None and "store" in pending_prices:
        return True
    return db.scalar(
        select(PriceBook.id)
        .where(
            PriceBook.project_id == project_id,
            PriceBook.price_type == "store",
            PriceBook.amount_cents >= 0,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > datetime.now(UTC)),
        )
        .limit(1)
    ) is not None


def _commit_project_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="项目编码或价格数据冲突") from exc


@router.post("/projects")
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_catalog_master_admin(staff)
    data = body.model_dump(exclude={"prices"})
    project = Project(**data)
    db.add(project)
    db.flush()
    _append_project_prices(db, project.id, body.prices, staff.name)
    _audit(db, staff, "create_project", "project", project.code, store_id=project.store_id)
    _commit_project_or_conflict(db)
    return {"id": project.id, "code": project.code}


def _update_project_strict(project_id: int, body: ProjectPatch, db: Session, staff: Staff) -> dict:
    project, referrers = _locked_project_for_update(db, project_id, staff)
    _require_catalog_write(
        staff,
        set(body.model_fields_set),
        publication_status=body.publication_status,
        current_publication_status=project.publication_status,
    )
    data = body.model_dump(exclude_unset=True, exclude={"prices"})
    if "code" in data and data["code"] != project.code and referrers:
        raise HTTPException(status_code=409, detail="已发布目录引用的项目编码不可直接修改")
    if data.get("publication_status") in {"inactive", "archived"} and referrers:
        raise HTTPException(status_code=409, detail="仍被已发布目录引用的项目不可停用或归档")
    if data.get("publication_status") == "published" and not _has_project_store_price(
        db,
        project.id,
        body.prices if "prices" in body.model_fields_set else None,
    ):
        raise HTTPException(status_code=422, detail="正式项目必须配置非负门店价")
    for key, value in data.items():
        setattr(project, key, value)
    if "prices" in body.model_fields_set:
        _append_project_prices(db, project.id, body.prices or {}, staff.name)
    _audit(db, staff, "update_project", "project", str(project.id), store_id=project.store_id)
    _commit_project_or_conflict(db)
    return {"ok": True, "id": project.id, "code": project.code, "publication_status": project.publication_status}


@router.patch("/projects/{proj_id}")
def patch_project(proj_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                  authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    return _update_project_strict(proj_id, body, db, staff)


@router.post("/projects/{proj_id}")
def update_project(proj_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    """保留旧 POST 路径，但使用与 PATCH 完全相同的严格契约。"""
    staff = _current_staff(authorization, db)
    return _update_project_strict(proj_id, body, db, staff)


@router.post("/projects/{proj_id}/duplicate")
def duplicate_project(proj_id: int, body: ProjectDuplicateIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_catalog_master_admin(staff)
    source, _ = _locked_project_for_update(db, proj_id, staff)
    duplicate = Project(
        store_id=source.store_id,
        code=body.code,
        category=source.category,
        category_mark=source.category_mark,
        name=body.name,
        duration_min=source.duration_min,
        summary=source.summary,
        image_url=source.image_url,
        tags=list(source.tags or []),
        detail_modules=list(source.detail_modules or []),
        diy_options=[],
        display_order=source.display_order,
        price_label=source.price_label,
        publication_status="draft",
    )
    db.add(duplicate)
    db.flush()
    latest_prices: dict[str, PriceBook] = {}
    for price in db.scalars(
        select(PriceBook)
        .where(
            PriceBook.project_id == source.id,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > datetime.now(UTC)),
        )
        .order_by(PriceBook.price_type, PriceBook.published_at.desc(), PriceBook.id.desc())
    ):
        latest_prices.setdefault(price.price_type, price)
    _append_project_prices(
        db,
        duplicate.id,
        {price_type: int(price.amount_cents) for price_type, price in latest_prices.items()},
        staff.name,
    )
    draft = ProjectCatalogVersion(project_id=duplicate.id, version=1, status="draft")
    db.add(draft)
    db.flush()
    if source.current_published_version_id is not None:
        try:
            copy_catalog_version_graph(db, source.current_published_version_id, draft.id)
        except CatalogDomainError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="源项目已发布目录快照校验失败") from exc
    _audit(db, staff, "duplicate_project", "project", str(source.id), {"duplicate_project_id": duplicate.id})
    _commit_project_or_conflict(db)
    return {"id": duplicate.id, "code": duplicate.code, "catalog_version_id": draft.id}


@router.post("/projects/{proj_id}/archive")
def archive_project(proj_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_catalog_master_admin(staff)
    return _update_project_strict(
        proj_id,
        ProjectPatch(publication_status="archived"),
        db,
        staff,
    )


# ──────────────────────────────────────────────────────
# 4. 加项管理（结构化 DIY 配置）
# ──────────────────────────────────────────────────────

class AddonIn(BaseModel):
    store_id: int
    code: str
    name: str
    parent_project_id: int | None = None
    duration_min: int | None = None
    summary: str = ""
    image_url: str = ""
    display_order: int = 0
    chargeable: bool = True
    store_price_cents: int = 0
    member_price_cents: int | None = None
    member_price_enabled: bool = False
    independently_sellable: bool = False
    can_attach_to_parent: bool = True
    publication_status: str = "draft"


class AddonPatchIn(BaseModel):
    code: str | None = None
    name: str | None = None
    parent_project_id: int | None = None
    duration_min: int | None = None
    summary: str | None = None
    image_url: str | None = None
    display_order: int | None = None
    chargeable: bool | None = None
    store_price_cents: int | None = None
    member_price_cents: int | None = None
    member_price_enabled: bool | None = None
    independently_sellable: bool | None = None
    can_attach_to_parent: bool | None = None
    publication_status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_for_non_nullable_fields(cls, data):
        if isinstance(data, dict):
            non_nullable = {"summary", "image_url", "store_price_cents", "publication_status"}
            invalid = sorted(field for field in non_nullable if field in data and data[field] is None)
            if invalid:
                raise ValueError(f"{', '.join(invalid)} 不允许为 null")
        return data


def _validate_addon_payload(db: Session, body: AddonIn, store_id: int) -> None:
    if body.publication_status not in {"draft", "candidate", "published", "inactive", "archived"}:
        raise HTTPException(status_code=400, detail="加项发布状态无效")
    if body.parent_project_id is not None:
        project = db.get(Project, body.parent_project_id)
        if not project or project.store_id != store_id:
            raise HTTPException(status_code=400, detail="关联主项目不存在或不属于当前门店")
    if body.store_price_cents < 0 or (body.member_price_cents is not None and body.member_price_cents < 0):
        raise HTTPException(status_code=400, detail="加项价格不能为负数")
    if not body.chargeable and any((body.store_price_cents, body.member_price_cents or 0, body.member_price_enabled)):
        raise HTTPException(status_code=400, detail="免费选项不能配置会员价格或金额")
    if body.member_price_enabled and body.member_price_cents is None:
        raise HTTPException(status_code=400, detail="启用会员价时必须填写会员价")
    if body.member_price_enabled and body.member_price_cents > body.store_price_cents:
        raise HTTPException(status_code=400, detail="会员价不能高于门店价")


def _addon_view(addon: Addon) -> dict:
    store_price = int(addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents)
    return {
        "id": addon.id,
        "store_id": addon.store_id,
        "code": addon.code,
        "name": addon.name,
        "parent_project_id": addon.parent_project_id,
        "duration_min": addon.duration_min,
        "summary": addon.summary,
        "image_url": addon.image_url,
        "display_order": addon.display_order,
        "chargeable": addon.chargeable,
        "store_price_cents": store_price,
        "member_price_cents": addon.member_price_cents,
        "member_price_enabled": addon.member_price_enabled,
        "independently_sellable": addon.independently_sellable,
        "can_attach_to_parent": addon.can_attach_to_parent,
        "publication_status": addon.publication_status,
    }


@router.get("/addons")
def list_addons_admin(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    parent_project_id: int | None = Query(None),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    stmt = select(Addon)
    if not _is_headquarters_admin(staff):
        scoped_store_id = _scoped_store_id(staff, store_id)
        stmt = stmt.where(Addon.store_id == scoped_store_id)
    elif store_id is not None:
        stmt = stmt.where(Addon.store_id == store_id)
    if status:
        stmt = stmt.where(Addon.publication_status == status)
    if parent_project_id is not None:
        stmt = stmt.where(Addon.parent_project_id == parent_project_id)
    if page is None and page_size is None:
        return [_addon_view(addon) for addon in db.scalars(stmt.order_by(Addon.display_order, Addon.id))]
    resolved_page = page or 1
    resolved_page_size = page_size or 50
    total = db.scalar(select(sa_func.count()).select_from(stmt.subquery())) or 0
    addons = db.scalars(
        stmt.order_by(Addon.display_order, Addon.id)
        .offset((resolved_page - 1) * resolved_page_size)
        .limit(resolved_page_size)
    ).all()
    return {
        "items": [_addon_view(addon) for addon in addons],
        "total": total,
        "page": resolved_page,
        "page_size": resolved_page_size,
    }


@router.post("/addons")
def create_addon(body: AddonIn, db: Session = Depends(get_db), authorization: str | None = Header(None)) -> dict:
    staff = _current_staff(authorization, db)
    _require_catalog_master_admin(staff)
    store_id = body.store_id
    if db.scalar(select(Addon).where(Addon.code == body.code)):
        raise HTTPException(status_code=409, detail="加项编码已存在")
    _validate_addon_payload(db, body, store_id)
    addon_data = body.model_dump()
    addon_data.update({
        "price_cents": body.store_price_cents if body.chargeable else 0,
        "store_price_cents": body.store_price_cents if body.chargeable else 0,
        "member_price_cents": body.member_price_cents if body.chargeable else None,
        "member_price_enabled": body.member_price_enabled if body.chargeable else False,
    })
    addon = Addon(**addon_data)
    db.add(addon)
    db.flush()
    _audit(db, staff, "create_addon", "addon", str(addon.id), {"code": addon.code})
    db.commit()
    db.refresh(addon)
    return _addon_view(addon)


@router.post("/addons/{addon_id}")
@router.patch("/addons/{addon_id}")
def update_addon(addon_id: int, body: AddonPatchIn, db: Session = Depends(get_db), authorization: str | None = Header(None)) -> dict:
    staff = _current_staff(authorization, db)
    addon = db.get(Addon, addon_id) if _is_headquarters_admin(staff) else _require_owned(
        db.get(Addon, addon_id), staff, "加项不存在"
    )
    if not addon:
        raise HTTPException(status_code=404, detail="加项不存在")
    patch_values = body.model_dump(exclude_unset=True)
    fields = set(patch_values)
    _require_catalog_write(
        staff,
        fields,
        publication_status=body.publication_status,
        current_publication_status=addon.publication_status,
    )
    current = _addon_view(addon)
    merged = AddonIn(
        store_id=addon.store_id,
        code=patch_values["code"] if "code" in patch_values else addon.code,
        name=patch_values["name"] if "name" in patch_values else addon.name,
        parent_project_id=patch_values["parent_project_id"] if "parent_project_id" in patch_values else addon.parent_project_id,
        duration_min=patch_values["duration_min"] if "duration_min" in patch_values else addon.duration_min,
        summary=patch_values["summary"] if "summary" in patch_values and patch_values["summary"] is not None else addon.summary,
        image_url=patch_values["image_url"] if "image_url" in patch_values and patch_values["image_url"] is not None else addon.image_url,
        display_order=patch_values["display_order"] if "display_order" in patch_values else addon.display_order,
        chargeable=patch_values["chargeable"] if "chargeable" in patch_values else addon.chargeable,
        store_price_cents=patch_values["store_price_cents"] if "store_price_cents" in patch_values and patch_values["store_price_cents"] is not None else current["store_price_cents"],
        member_price_cents=patch_values["member_price_cents"] if "member_price_cents" in patch_values else (
            addon.member_price_cents if addon.member_price_enabled else None
        ),
        member_price_enabled=patch_values["member_price_enabled"] if "member_price_enabled" in patch_values else addon.member_price_enabled,
        independently_sellable=patch_values["independently_sellable"] if "independently_sellable" in patch_values else addon.independently_sellable,
        can_attach_to_parent=patch_values["can_attach_to_parent"] if "can_attach_to_parent" in patch_values else addon.can_attach_to_parent,
        publication_status=patch_values["publication_status"] if "publication_status" in patch_values and patch_values["publication_status"] is not None else addon.publication_status,
    )
    duplicate = db.scalar(select(Addon).where(Addon.code == merged.code, Addon.id != addon.id))
    if duplicate:
        raise HTTPException(status_code=409, detail="加项编码已存在")
    _validate_addon_payload(db, merged, addon.store_id)
    for key, value in merged.model_dump().items():
        if key != "store_id":
            setattr(addon, key, value)
    addon.price_cents = merged.store_price_cents if merged.chargeable else 0
    addon.store_price_cents = merged.store_price_cents if merged.chargeable else 0
    addon.member_price_cents = merged.member_price_cents if merged.chargeable else None
    addon.member_price_enabled = merged.member_price_enabled if merged.chargeable else False
    _audit(db, staff, "update_addon", "addon", str(addon.id))
    db.commit()
    db.refresh(addon)
    return _addon_view(addon)


# ──────────────────────────────────────────────────────
# 5. 商品管理（管理端 CRUD）
# ──────────────────────────────────────────────────────

@router.get("/products")
def list_products_admin(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    product_type: str | None = Query(None),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    q = select(Product)
    if not _is_headquarters_admin(staff):
        scoped_store_id = _scoped_store_id(staff, store_id)
        q = q.where(Product.store_id == scoped_store_id)
    elif store_id is not None:
        q = q.where(Product.store_id == store_id)
    if status:
        q = q.where(Product.publication_status == status)
    if product_type:
        q = q.where(Product.product_type == product_type)
    if page is None and page_size is None:
        return [_product_view(product) for product in db.execute(q.order_by(Product.id)).scalars().all()]

    resolved_page = page or 1
    resolved_page_size = page_size or 50
    total = db.scalar(select(sa_func.count()).select_from(q.subquery())) or 0
    products = db.execute(
        q.order_by(Product.id).offset((resolved_page - 1) * resolved_page_size).limit(resolved_page_size),
    ).scalars().all()
    return {
        "items": [_product_view(product) for product in products],
        "total": total,
        "page": resolved_page,
        "page_size": resolved_page_size,
    }


class ProductIn(BaseModel):
    store_id: int
    code: str
    name: str
    desc: str = ""
    spec: str = ""
    product_type: str = "foot"
    price_cents: int = 990
    image_url: str = ""
    publication_status: str = "draft"


ProductPublicationStatus = Literal["draft", "candidate", "published", "inactive", "archived"]


class ProductPatch(BaseModel):
    """商品主数据的部分更新；门店店长最终只允许提交 publication_status。"""

    model_config = ConfigDict(extra="forbid")

    code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    desc: StrictStr | None = Field(default=None, max_length=256)
    spec: StrictStr | None = Field(default=None, max_length=64)
    product_type: StrictStr | None = Field(default=None, min_length=1, max_length=16)
    price_cents: StrictInt | None = Field(default=None, ge=0)
    image_url: StrictStr | None = Field(default=None, max_length=512)
    publication_status: ProductPublicationStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_nulls(cls, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if item is None:
                    raise ValueError(f"{key} must not be null")
        return value


def _product_view(product: Product) -> dict:
    return {
        "id": product.id,
        "store_id": product.store_id,
        "code": product.code,
        "name": product.name,
        "desc": product.desc,
        "spec": product.spec,
        "product_type": product.product_type,
        "price_cents": product.price_cents,
        "image_url": product.image_url,
        "publication_status": product.publication_status,
    }


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_catalog_master_admin(s)
    p = Product(**body.model_dump())
    db.add(p)
    _audit(db, s, "create_product", "product", body.code, store_id=p.store_id)
    db.commit()
    return {"id": p.id, "code": p.code}


def _update_product(prod_id: int, body: ProductPatch, db: Session, staff: Staff) -> dict:
    fields = set(body.model_fields_set)
    p = db.get(Product, prod_id) if _is_headquarters_admin(staff) else _require_owned(db.get(Product, prod_id), staff, "商品不存在")
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    _require_catalog_write(
        staff,
        fields,
        publication_status=body.publication_status,
        current_publication_status=p.publication_status,
    )
    for key, value in body.model_dump(exclude_unset=True).items():
        if key != "store_id":
            setattr(p, key, value)
    _audit(db, staff, "update_product", "product", str(prod_id), store_id=p.store_id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="商品编码冲突") from exc
    db.refresh(p)
    return _product_view(p)


@router.patch("/products/{prod_id}")
def patch_product(prod_id: int, body: ProductPatch, db: Session = Depends(get_db),
                  authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    return _update_product(prod_id, body, db, s)


@router.post("/products/{prod_id}")
def update_product(prod_id: int, body: dict, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    """保留旧 POST 路径：接受历史完整对象，忽略非商品字段并保留旧响应。"""
    s = _current_staff(authorization, db)
    known_fields = {key: value for key, value in body.items() if key in ProductPatch.model_fields}
    try:
        patch = ProductPatch.model_validate(known_fields)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc
    _update_product(prod_id, patch, db, s)
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 5. 用户标签管理
# ──────────────────────────────────────────────────────

@router.get("/tags")
def list_tags(db: Session = Depends(get_db),
              authorization: str | None = Header(None)) -> list:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    tags = db.execute(select(CustomerTag).where(
        CustomerTag.store_id == store_id,
    ).order_by(CustomerTag.id)).scalars().all()
    return [{
        "id": t.id, "name": t.name, "color": t.color,
        "tag_type": t.tag_type, "description": t.description,
        "auto_rule": t.auto_rule, "status": t.status,
        "user_count": db.scalar(
            select(sa_func.count()).select_from(CustomerTagRelation)
            .where(CustomerTagRelation.tag_id == t.id)
        ),
    } for t in tags]


class TagIn(BaseModel):
    name: str
    color: str = "#1f8f75"
    tag_type: str = "manual"
    description: str = ""
    auto_rule: dict | None = None


PROFILE_SOURCE_VALUES = {"customer_statement", "service_observation", "both"}
PROFILE_FIELD_OPTIONS = {
    "age_range": {"18-25", "26-35", "31-40", "36-45", "46岁以上", "46-55", "56+", "不确定"},
    "gender": {"男", "女", "不记录"},
    "body_type": {"偏瘦", "标准", "匀称", "偏壮", "不记录"},
    "occupation": {"久坐", "久站", "体力工作", "教师", "办公室工作", "服务业", "自由职业", "学生", "退休", "其他", "不记录"},
}
PROFILE_PRESET_SIGNALS = {
    "肩颈紧张", "腰部不适", "腿部酸胀", "局部紧绷", "放松需求",
    "偏好轻柔力度", "偏好中等力度", "偏好强力力度",
}
PROFILE_FORCE_SIGNALS = {"偏好轻柔力度", "偏好中等力度", "偏好强力力度"}
PROFILE_FORBIDDEN_WORDS = ("确诊", "诊断", "疾病", "治疗", "治愈", "疗效", "癌", "处方")
PROFILE_PRIVATE_WORDS = ("微信", "手机号", "电话", "座机", "联系方式", "qq", "消费能力", "有钱", "贫穷", "性格", "人格")
PROFILE_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PROFILE_MOBILE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
PROFILE_LANDLINE_PATTERN = re.compile(r"(?<!\d)0\d{9,11}(?!\d)")


def _contains_private_profile_content(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"[\s\-()（）]", "", normalized)
    return (
        any(word in normalized.lower() for word in PROFILE_PRIVATE_WORDS)
        or bool(PROFILE_EMAIL_PATTERN.search(normalized))
        or bool(PROFILE_MOBILE_PATTERN.search(compact))
        or bool(PROFILE_LANDLINE_PATTERN.search(compact))
    )

ServiceArea = Literal["neck_shoulder", "waist_hip", "legs", "abdomen", "feet", "full_relaxation"]
AvoidArea = Literal["neck_shoulder", "waist_hip", "legs", "abdomen", "feet"]


def _reject_duplicate_codes(value: list[str]) -> list[str]:
    if len(value) != len(set(value)):
        raise ValueError("服务参考选项不能重复")
    return value


class ServiceReferenceCustomerReported(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_areas: list[ServiceArea] = Field(default_factory=list, max_length=6)
    avoid_areas: list[AvoidArea] = Field(default_factory=list, max_length=5)
    force_preference: Literal["gentle", "medium", "strong"] | None = None
    temperature_preference: Literal["lower", "medium", "higher"] | None = None
    quote: str = Field(default="", max_length=100)

    @field_validator("focus_areas", "avoid_areas")
    @classmethod
    def validate_unique_areas(cls, value: list[str]) -> list[str]:
        return _reject_duplicate_codes(value)

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, value: str) -> str:
        text = value.strip()
        if any(word in text for word in PROFILE_FORBIDDEN_WORDS):
            raise ValueError("服务参考仅支持非医疗描述，请勿填写诊断或治疗结论")
        if _contains_private_profile_content(text):
            raise ValueError("顾客原话请勿填写联系方式、消费能力或人格评价")
        return text


class ServiceReferenceTechnicianObserved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_feedback: Literal["suitable", "better_after_adjustment", "adjust_next_time"] | None = None


class ServiceReferenceNextVisit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Literal["repeat_current", "confirm_on_arrival"] | None = None


class ServiceReferenceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    taxonomy_version: Literal["service_reference_v1"]
    customer_reported: ServiceReferenceCustomerReported = Field(default_factory=ServiceReferenceCustomerReported)
    technician_observed: ServiceReferenceTechnicianObserved = Field(default_factory=ServiceReferenceTechnicianObserved)
    next_visit: ServiceReferenceNextVisit = Field(default_factory=ServiceReferenceNextVisit)

    def storage_payload(self) -> dict:
        return self.model_dump(mode="json", exclude_unset=True, exclude_none=True)

    def has_content(self) -> bool:
        reported = self.customer_reported
        return bool(
            reported.focus_areas
            or reported.avoid_areas
            or reported.force_preference
            or reported.temperature_preference
            or reported.quote
            or self.technician_observed.service_feedback
            or self.next_visit.plan
        )


class CustomerProfileRecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    selection_session_id: str | None = None
    technician_id: int | None = None
    source: Literal["customer_statement", "service_observation", "both"] = "customer_statement"
    schema_version: Literal[1, 2] = 1
    taxonomy_version: Literal["service_reference_v1"] | None = None
    customer_confirmed: StrictBool = False
    profile: dict[str, StrictStr] | ServiceReferenceProfile = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field(default="", max_length=500)
    correction_of_id: int | None = None
    correction_reason: str = Field(default="", max_length=256)

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: dict[str, str] | ServiceReferenceProfile) -> dict[str, str] | ServiceReferenceProfile:
        if isinstance(value, ServiceReferenceProfile):
            return value
        unknown_fields = set(value) - set(PROFILE_FIELD_OPTIONS)
        if unknown_fields:
            raise ValueError("画像基础信息包含不支持的字段")
        cleaned: dict[str, str] = {}
        for field, raw in value.items():
            text = raw.strip()
            if not text or text == "不记录":
                continue
            if text not in PROFILE_FIELD_OPTIONS[field]:
                raise ValueError(f"{field} 不是支持的选项")
            if any(word in text for word in PROFILE_FORBIDDEN_WORDS):
                raise ValueError("画像记录仅支持非医疗描述，请勿填写诊断或治疗结论")
            cleaned[field] = text
        return cleaned

    @field_validator("signals")
    @classmethod
    def validate_signals(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text or len(text) > 64:
                raise ValueError("画像标签长度不合法")
            if any(word in text for word in PROFILE_FORBIDDEN_WORDS):
                raise ValueError("画像记录仅支持非医疗描述，请勿填写诊断或治疗结论")
            if text not in cleaned:
                cleaned.append(text)
        if len(set(cleaned) & PROFILE_FORCE_SIGNALS) > 1:
            raise ValueError("力度偏好只能选择一项")
        return cleaned

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        text = value.strip()
        if any(word in text for word in PROFILE_FORBIDDEN_WORDS):
            raise ValueError("画像记录仅支持非医疗描述，请勿填写诊断或治疗结论")
        return text

    @model_validator(mode="after")
    def validate_service_reference_version(self):
        if self.schema_version == 2:
            if self.taxonomy_version != "service_reference_v1" or not isinstance(self.profile, ServiceReferenceProfile):
                raise ValueError("v2 服务参考必须使用 service_reference_v1 结构")
            if self.profile.schema_version != self.schema_version or self.profile.taxonomy_version != self.taxonomy_version:
                raise ValueError("服务参考内外版本必须一致")
            if self.signals or self.note:
                raise ValueError("v2 服务参考不能混用旧版标签或备注")
            if not self.profile.has_content():
                raise ValueError("请至少记录一项服务参考")
            self.source = "both" if self.customer_confirmed else "service_observation"
        elif self.taxonomy_version is not None or self.customer_confirmed or isinstance(self.profile, ServiceReferenceProfile):
            raise ValueError("旧版画像不能携带 v2 服务参考元数据")
        return self

@router.post("/tags")
def create_tag(body: TagIn, db: Session = Depends(get_db),
               authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    store_id = _staff_store_id(s)
    if db.scalar(select(CustomerTag).where(CustomerTag.store_id == store_id, CustomerTag.name == body.name)):
        raise HTTPException(400, "标签名已存在")
    t = CustomerTag(store_id=store_id, **body.model_dump())
    db.add(t)
    _audit(db, s, "create_tag", "tag", body.name)
    db.commit()
    return {"id": t.id}


@router.post("/tags/{tag_id}")
def update_tag(tag_id: int, body: dict, db: Session = Depends(get_db),
               authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    t = db.scalar(select(CustomerTag).where(
        CustomerTag.id == tag_id,
        CustomerTag.store_id == _staff_store_id(s),
    ))
    if not t:
        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(t, k) and k != "id":
            setattr(t, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db),
               authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    t = db.scalar(select(CustomerTag).where(
        CustomerTag.id == tag_id,
        CustomerTag.store_id == _staff_store_id(s),
    ))
    if not t:
        raise HTTPException(404)
    # 删除关联
    db.execute(select(CustomerTagRelation).where(CustomerTagRelation.tag_id == tag_id)).scalars()
    rels = db.execute(
        select(CustomerTagRelation).where(CustomerTagRelation.tag_id == tag_id)
    ).scalars().all()
    for r in rels:
        db.delete(r)
    db.delete(t)
    db.commit()
    return {"ok": True}


def _profile_record_view(record: CustomerProfileRecord, db: Session) -> dict:
    creator = db.get(Staff, record.created_by_staff_id)
    technician = db.get(Technician, record.technician_id) if record.technician_id else None
    return {
        "id": record.id,
        "store_id": record.store_id,
        "user_id": record.user_id,
        "selection_session_id": record.selection_session_id,
        "technician_id": record.technician_id,
        "technician_name": technician.name if technician else None,
        "created_by_staff_id": record.created_by_staff_id,
        "created_by_name": creator.name if creator else "",
        "source": record.source or "customer_statement",
        "schema_version": record.schema_version or 1,
        "taxonomy_version": record.taxonomy_version,
        "customer_confirmed": bool(record.customer_confirmed),
        "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
        "profile": record.profile or {},
        "signals": record.signals or [],
        "note": record.note,
        "correction_of_id": record.correction_of_id,
        "correction_reason": record.correction_reason,
        "disclaimer": "仅作到店服务参考，不构成医疗建议",
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _profile_payload(body: CustomerProfileRecordIn) -> dict:
    if isinstance(body.profile, ServiceReferenceProfile):
        return body.profile.storage_payload()
    return body.profile


def _profile_request_fingerprint(body: CustomerProfileRecordIn, technician_id: int | None) -> str:
    payload = {
        "user_id": body.user_id,
        "selection_session_id": body.selection_session_id,
        "technician_id": technician_id,
        "source": body.source,
        "schema_version": body.schema_version,
        "taxonomy_version": body.taxonomy_version,
        "customer_confirmed": body.customer_confirmed,
        "profile": _profile_payload(body),
        "signals": body.signals,
        "note": body.note,
        "correction_of_id": body.correction_of_id,
        "correction_reason": body.correction_reason.strip(),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _same_profile_request(record: CustomerProfileRecord, body: CustomerProfileRecordIn, technician_id: int | None) -> bool:
    return _profile_request_fingerprint(body, technician_id) == hashlib.sha256(json.dumps({
        "user_id": record.user_id,
        "selection_session_id": record.selection_session_id,
        "technician_id": record.technician_id,
        "source": record.source or "customer_statement",
        "schema_version": record.schema_version or 1,
        "taxonomy_version": record.taxonomy_version,
        "customer_confirmed": bool(record.customer_confirmed),
        "profile": record.profile or {},
        "signals": record.signals or [],
        "note": record.note or "",
        "correction_of_id": record.correction_of_id,
        "correction_reason": (record.correction_reason or "").strip(),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _require_profile_idempotency_key(idempotency_key: str | None) -> str:
    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 128:
        raise HTTPException(status_code=400, detail="画像记录必须携带长度为 8 至 128 的 Idempotency-Key")
    return key


@router.get("/service-orders")
def list_technician_service_orders(
    status: Literal["in_progress", "history"] = "in_progress",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    role = normalize_staff_role(staff.role, staff.technician_id)
    if role not in {"technician", "manager"}:
        raise HTTPException(status_code=403, detail="当前账号无权查看服务单")
    store_id = _staff_store_id(staff)
    statuses = TECHNICIAN_ACTIVE_SERVICE_STATUSES if status == "in_progress" else TECHNICIAN_HISTORY_SERVICE_STATUSES
    scoped = select(ServiceOrder).where(ServiceOrder.store_id == store_id, ServiceOrder.status.in_(statuses))
    total = db.scalar(select(sa_func.count()).select_from(scoped.subquery())) or 0
    rows = db.scalars(
        scoped.order_by(ServiceOrder.created_at.desc(), ServiceOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for service_order in rows:
        visit = db.get(Visit, service_order.visit_id)
        user = db.get(User, visit.user_id) if visit and visit.user_id else None
        items.append({
            "id": service_order.id,
            "visit_id": service_order.visit_id,
            "status": service_order.status,
            "items": _redact_technician_item(service_order.items or []),
            "customer": {
                "id": user.id if user else None,
                "nickname": user.nickname if user else "",
                "phone_masked": _mask_phone(user.phone) if user else "",
            },
            "started_at": service_order.started_at.isoformat() if service_order.started_at else None,
            "finished_at": service_order.finished_at.isoformat() if service_order.finished_at else None,
            "created_at": service_order.created_at.isoformat() if service_order.created_at else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/customers/{customer_id}/profile-records")
def create_profile_record(
    customer_id: int,
    body: ProfileRecordCreate,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    idempotency_key = _require_profile_idempotency_key(idempotency_key)
    _require_store_user(db, customer_id, staff)
    if not body.tags and not body.service_note:
        raise HTTPException(status_code=422, detail="请至少记录一项服务参考")
    existing = db.scalar(select(CustomerProfileRecord).where(
        CustomerProfileRecord.store_id == store_id,
        CustomerProfileRecord.created_by_staff_id == staff.id,
        CustomerProfileRecord.idempotency_key == idempotency_key,
    ))
    if existing:
        if (
            existing.user_id == customer_id
            and existing.selection_session_id is None
            and existing.technician_id is None
            and (existing.profile or {}) == {}
            and (existing.signals or []) == body.tags
            and (existing.note or "") == body.service_note
        ):
            return {
                "id": existing.id,
                "store_id": existing.store_id,
                "customer_id": existing.user_id,
                "technician_id": None,
                "disclaimer": "仅作到店服务参考，不构成医疗建议",
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    record = CustomerProfileRecord(
        store_id=store_id,
        user_id=customer_id,
        technician_id=None,
        created_by_staff_id=staff.id,
        source="customer_statement",
        idempotency_key=idempotency_key,
        profile={},
        signals=body.tags,
        note=body.service_note,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(CustomerProfileRecord).where(
            CustomerProfileRecord.store_id == store_id,
            CustomerProfileRecord.created_by_staff_id == staff.id,
            CustomerProfileRecord.idempotency_key == idempotency_key,
        ))
        if existing and existing.user_id == customer_id and (existing.signals or []) == body.tags and (existing.note or "") == body.service_note:
            return {
                "id": existing.id,
                "store_id": existing.store_id,
                "customer_id": existing.user_id,
                "technician_id": None,
                "disclaimer": "仅作到店服务参考，不构成医疗建议",
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    db.add(AuditLog(
        actor_type="staff", actor_id=str(staff.id), store_id=store_id,
        action="manager_create_customer_profile_record", entity_type="customer_profile_record", entity_id=str(record.id),
        detail={"customer_id": customer_id, "technician_id": None, "tags": body.tags, "idempotency_key": idempotency_key},
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(CustomerProfileRecord).where(
            CustomerProfileRecord.store_id == store_id,
            CustomerProfileRecord.created_by_staff_id == staff.id,
            CustomerProfileRecord.idempotency_key == idempotency_key,
        ))
        if existing and existing.user_id == customer_id and (existing.signals or []) == body.tags and (existing.note or "") == body.service_note:
            return {
                "id": existing.id,
                "store_id": existing.store_id,
                "customer_id": existing.user_id,
                "technician_id": None,
                "disclaimer": "仅作到店服务参考，不构成医疗建议",
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    db.refresh(record)
    response = {
        "id": record.id,
        "store_id": record.store_id,
        "customer_id": record.user_id,
        "technician_id": record.technician_id,
        "disclaimer": "仅作到店服务参考，不构成医疗建议",
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
    response.update({"tags": record.signals or [], "service_note": record.note})
    return response


@router.post("/customer-profile-records")
def create_customer_profile_record(
    body: CustomerProfileRecordIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    role = normalize_staff_role(staff.role, staff.technician_id)
    if role not in {"technician", "manager"}:
        raise HTTPException(status_code=403, detail="当前账号无权新增画像记录")
    idempotency_key = _require_profile_idempotency_key(idempotency_key)
    is_bound_technician = role == "technician" and bool(staff.technician_id)
    if is_bound_technician and body.schema_version == 1 and "source" not in body.model_fields_set:
        raise HTTPException(status_code=422, detail="技师记录必须明确选择记录来源")
    if is_bound_technician and (body.technician_id is not None or body.correction_of_id is not None):
        raise HTTPException(status_code=403, detail="技师不能代填他人画像或更正历史记录")
    technician_id = staff.technician_id if is_bound_technician else body.technician_id
    if is_bound_technician:
        if not body.selection_session_id:
            raise HTTPException(status_code=403, detail="技师画像记录必须关联已完成服务")
    if body.schema_version == 2 and not body.selection_session_id:
        raise HTTPException(status_code=422, detail="v2 服务参考必须关联已完成服务")
    _require_store_user(db, body.user_id, staff)
    if not _profile_payload(body) and not body.signals and not body.note:
        raise HTTPException(status_code=422, detail="请至少记录一项服务参考")
    unsupported_signals = [signal for signal in body.signals if signal not in PROFILE_PRESET_SIGNALS and not db.scalar(select(CustomerTag.id).where(
        CustomerTag.store_id == store_id,
        CustomerTag.name == signal,
        CustomerTag.status == "active",
    ))]
    if unsupported_signals:
        raise HTTPException(status_code=422, detail="服务观察仅支持预设项或本门店启用标签")
    existing = db.scalar(select(CustomerProfileRecord).where(
        CustomerProfileRecord.store_id == store_id,
        CustomerProfileRecord.created_by_staff_id == staff.id,
        CustomerProfileRecord.idempotency_key == idempotency_key,
    ))
    if existing:
        if _same_profile_request(existing, body, technician_id):
            return _profile_record_view(existing, db)
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    if body.selection_session_id:
        session = db.get(SelectionSession, body.selection_session_id)
        if not session or session.store_id != store_id or session.customer_id != body.user_id:
            raise HTTPException(status_code=404, detail="本次服务记录不存在")
        occupancy = db.scalar(select(PositionOccupancy).where(
            PositionOccupancy.selection_session_id == session.id,
        ).order_by(PositionOccupancy.id.desc()))
        if not occupancy or not occupancy.actual_service_end_at:
            raise HTTPException(status_code=409, detail="服务完成后才能记录顾客画像")
        if is_bound_technician:
            service_audit = db.scalar(select(AuditLog).where(
                AuditLog.store_id == store_id,
                AuditLog.actor_type == "staff",
                AuditLog.actor_id == str(staff.id),
                AuditLog.action == "technician_finish_service",
                AuditLog.entity_type == "position_occupancy",
                # 以完成服务的占用实体作为权威关联。历史审计 detail 可能缺失或被
                # 序列化为不同类型，不能仅依赖其中的 selection_session_id。
                AuditLog.entity_id == str(occupancy.id),
            ))
            if not service_audit:
                raise HTTPException(status_code=403, detail="技师只能记录本人完成服务的顾客画像")
    if technician_id:
        technician = db.get(Technician, technician_id)
        if not technician or technician.store_id != store_id:
            raise HTTPException(status_code=404, detail="技师不存在")
    if body.correction_of_id is not None:
        original = db.scalar(select(CustomerProfileRecord).where(
            CustomerProfileRecord.id == body.correction_of_id,
            CustomerProfileRecord.store_id == store_id,
            CustomerProfileRecord.user_id == body.user_id,
        ))
        if not original:
            raise HTTPException(status_code=404, detail="原画像记录不存在")
        if not body.correction_reason.strip():
            raise HTTPException(status_code=422, detail="更正记录需要填写原因")
    record = CustomerProfileRecord(
        store_id=store_id,
        user_id=body.user_id,
        selection_session_id=body.selection_session_id,
        technician_id=technician_id,
        created_by_staff_id=staff.id,
        profile=_profile_payload(body),
        signals=body.signals,
        note=body.note,
        correction_of_id=body.correction_of_id,
        correction_reason=body.correction_reason.strip(),
        source=body.source,
        schema_version=body.schema_version,
        taxonomy_version=body.taxonomy_version,
        customer_confirmed=body.customer_confirmed,
        confirmed_at=datetime.now(timezone.utc) if body.customer_confirmed else None,
        idempotency_key=idempotency_key,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(CustomerProfileRecord).where(
            CustomerProfileRecord.store_id == store_id,
            CustomerProfileRecord.created_by_staff_id == staff.id,
            CustomerProfileRecord.idempotency_key == idempotency_key,
        ))
        if existing and _same_profile_request(existing, body, technician_id):
            return _profile_record_view(existing, db)
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    # 已存在的门店运营标签自动建立关联；画像原始信号仍保留在记录快照中，避免跨门店污染标签字典。
    for signal in body.signals:
        tag = db.scalar(select(CustomerTag).where(
            CustomerTag.store_id == store_id,
            CustomerTag.name == signal,
            CustomerTag.status == "active",
        ))
        if tag and not db.scalar(select(CustomerTagRelation).where(
            CustomerTagRelation.user_id == body.user_id,
            CustomerTagRelation.tag_id == tag.id,
        )):
            db.add(CustomerTagRelation(user_id=body.user_id, tag_id=tag.id, source="profile"))
    _audit(db, staff, "create_customer_profile_record", "user", str(body.user_id), {
        "record_id": record.id,
        "selection_session_id": body.selection_session_id,
        "technician_id": technician_id,
        "source": body.source,
        "idempotency_key": idempotency_key,
        "signals": body.signals,
    })
    if not is_bound_technician and technician_id:
        _audit(db, staff, "manager_entered_customer_profile_record", "user", str(body.user_id), {
            "record_id": record.id,
            "technician_id": technician_id,
        })
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(CustomerProfileRecord).where(
            CustomerProfileRecord.store_id == store_id,
            CustomerProfileRecord.created_by_staff_id == staff.id,
            CustomerProfileRecord.idempotency_key == idempotency_key,
        ))
        if existing and _same_profile_request(existing, body, technician_id):
            return _profile_record_view(existing, db)
        raise HTTPException(status_code=409, detail="该幂等键已用于内容不同的画像记录")
    db.refresh(record)
    return _profile_record_view(record, db)


@router.get("/users/{user_id}/customer-profile-records")
def list_customer_profile_records(
    user_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) == "technician":
        raise HTTPException(status_code=403, detail="技师端不提供顾客历史画像读取")
    _require_store_user(db, user_id, staff)
    records = db.scalars(select(CustomerProfileRecord).where(
        CustomerProfileRecord.store_id == _staff_store_id(staff),
        CustomerProfileRecord.user_id == user_id,
    ).order_by(CustomerProfileRecord.created_at.desc(), CustomerProfileRecord.id.desc())).all()
    return {"items": [_profile_record_view(record, db) for record in records]}


# ──────────────────────────────────────────────────────
# 6. 用户列表（带标签/分层筛选 + 打标/移除标签）
# ──────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    tag_id: int | None = Query(None),
    segment_id: int | None = Query(None),
    search: str | None = Query(None),
    is_member: bool | None = Query(None),
    page: int = 1, page_size: int = 30,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> Paginated:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    q = select(User).where(User.id.in_(_store_user_ids(store_id)))
    if tag_id:
        sub = select(CustomerTagRelation.user_id).where(
            CustomerTagRelation.tag_id == tag_id,
            CustomerTagRelation.tag_id.in_(select(CustomerTag.id).where(CustomerTag.store_id == store_id)),
        )
        q = q.where(User.id.in_(sub))
    if segment_id:
        seg = db.get(CustomerSegment, segment_id)
        if seg and seg.conditions:
            conds = seg.conditions
            if "tags" in conds:
                tag_names = conds["tags"]
                tag_ids_sub = select(CustomerTag.id).where(
                    CustomerTag.store_id == store_id,
                    CustomerTag.name.in_(tag_names),
                )
                tagged_users = select(CustomerTagRelation.user_id).where(
                    CustomerTagRelation.tag_id.in_(tag_ids_sub)
                )
                q = q.where(User.id.in_(tagged_users))
            if conds.get("is_member"):
                q = q.where(User.is_member == True)
            if conds.get("total_spend_gt"):
                # 子查询：已完成订单总额
                spend_sub = (
                    select(Order.user_id, sa_func.sum(Order.pay_amount_cents).label("total"))
                    .where(Order.status == "completed", Order.store_id == store_id)
                    .group_by(Order.user_id)
                    .having(sa_func.sum(Order.pay_amount_cents) > conds["total_spend_gt"])
                    .subquery()
                )
                q = q.where(User.id.in_(select(spend_sub.c.user_id)))
    if search:
        search_term = search.strip()
        if search_term:
            q = q.where(or_(
                User.nickname.ilike(f"%{search_term}%"),
                User.phone.ilike(f"%{search_term}%"),
            ))
    if is_member is not None:
        q = q.where(User.is_member == is_member)
    q = q.order_by(User.id.desc())
    total = db.scalar(select(sa_func.count()).select_from(q.subquery()))
    users = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = []
    for u in users:
        tags_rel = db.execute(
            select(CustomerTagRelation).where(CustomerTagRelation.user_id == u.id)
        ).scalars().all()
        tag_info = []
        for tr in tags_rel:
            t = db.get(CustomerTag, tr.tag_id)
            if t:
                tag_info.append({"id": t.id, "name": t.name, "color": t.color})
        items.append({
            "id": u.id, "nickname": _customer_display_name(u),
            "phone_tail": u.phone[-4:] if u.phone else "",
            "phone_masked": _masked_phone(u.phone),
            "is_member": u.is_member, "member_type": u.member_type,
            "balance_cents": u.balance_cents,
            "tags": tag_info,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


class MembershipUpdateIn(BaseModel):
    """线下年度权益卡的严格周期输入。"""

    model_config = ConfigDict(extra="forbid")

    member_type: Literal["annual"] | None = None
    is_member: StrictBool | None = None
    cycle_id: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    member_started_at: datetime | None = None
    member_expire_at: datetime | None = None

    @field_validator("cycle_id")
    @classmethod
    def _cycle_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("cycle_id must not be blank")
        return value

    @field_validator("member_started_at", "member_expire_at")
    @classmethod
    def _membership_time_is_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("membership timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_transition(self):
        annual = self.member_type == "annual" or self.is_member is True
        cancelled = self.is_member is False
        if annual and cancelled:
            raise ValueError("annual membership cannot conflict with is_member=false")
        if not annual and not cancelled:
            raise ValueError("must provide annual enrollment or is_member=false")
        if cancelled:
            if any(value is not None for value in (self.member_type, self.cycle_id, self.member_started_at, self.member_expire_at)):
                raise ValueError("cancellation cannot include annual cycle fields")
            return self
        if not all((self.cycle_id, self.member_started_at, self.member_expire_at)):
            raise ValueError("annual membership requires cycle_id, member_started_at and member_expire_at")
        if self.member_expire_at <= self.member_started_at:
            raise ValueError("member_expire_at must be after member_started_at")
        return self


def _utc_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _same_instant(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    return _utc_time(left) == _utc_time(right)


def _grant_for_cycle(db: Session, user_id: int, cycle_id: str) -> MembershipBenefitGrant | None:
    return db.scalar(
        select(MembershipBenefitGrant)
        .where(
            MembershipBenefitGrant.user_id == user_id,
            MembershipBenefitGrant.membership_cycle_id == cycle_id,
        )
        .with_for_update()
    )


def _ensure_annual_cycle_grant(
    db: Session,
    user: User,
    cycle_id: str,
    started_at: datetime,
) -> MembershipBenefitGrant:
    grant = _grant_for_cycle(db, user.id, cycle_id)
    if grant is not None:
        return grant
    try:
        with db.begin_nested():
            grant = MembershipBenefitGrant(
                user_id=user.id,
                benefit_type="annual_project_gift",
                membership_cycle_id=cycle_id,
                membership_started_at=started_at,
                status="available",
            )
            db.add(grant)
            db.flush()
    except IntegrityError:
        grant = _grant_for_cycle(db, user.id, cycle_id)
        if grant is None:
            raise
    return grant


@router.patch("/users/{user_id}/membership")
def set_user_membership(user_id: int, body: MembershipUpdateIn, db: Session = Depends(get_db),
                        authorization: str | None = Header(None)):
    """仅接受带稳定周期和 aware 有效期的年度权益卡开通，或显式取消。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    user = _locked_store_user(db, user_id, staff)
    previous = user.is_member
    previous_member_type = user.member_type
    grant: MembershipBenefitGrant | None = None

    if body.is_member is False:
        user.is_member = False
        user.member_type = None
        # 保留 cycle/expiry 作为审计与同周期重开幂等依据，不能由取消制造新权益。
    else:
        assert body.cycle_id is not None
        assert body.member_started_at is not None
        assert body.member_expire_at is not None
        same_cycle = user.annual_membership_cycle_id == body.cycle_id
        if same_cycle:
            grant = _grant_for_cycle(db, user.id, body.cycle_id)
            if (
                grant is None
                or not _same_instant(grant.membership_started_at, body.member_started_at)
                or not _same_instant(user.member_expire_at, body.member_expire_at)
                or user.member_type not in {None, "annual"}
            ):
                raise HTTPException(status_code=409, detail="同一会员周期不能变更起止时间或会员类型")
        elif user.annual_membership_cycle_id is not None and user.member_expire_at is not None:
            if _utc_time(body.member_started_at) < _utc_time(user.member_expire_at):
                raise HTTPException(status_code=409, detail="续办周期开始时间不得早于上一周期到期时间")
        if grant is None:
            grant = _ensure_annual_cycle_grant(
                db,
                user,
                body.cycle_id,
                body.member_started_at,
            )
        user.is_member = True
        user.member_type = "annual"
        user.member_expire_at = body.member_expire_at
        user.annual_membership_cycle_id = body.cycle_id
        user.membership_store_id = _staff_store_id(staff)

    # 会员身份变化后，重算该顾客未完结选单的计价快照（draft/submitted）。
    from app.api.selections import refresh_session_pricing
    open_sessions = db.scalars(select(SelectionSession).where(
        SelectionSession.customer_id == user_id,
        SelectionSession.status.in_(["draft", "submitted"]),
    ))
    for session in open_sessions:
        refresh_session_pricing(db, session)
    _audit(db, staff, "set_membership", "user", str(user_id), {
        "is_member": user.is_member,
        "previous": previous,
        "previous_member_type": previous_member_type,
        "member_type": user.member_type,
        "membership_cycle_id": user.annual_membership_cycle_id,
        "membership_store_id": user.membership_store_id,
        "member_expire_at": user.member_expire_at.isoformat() if user.member_expire_at else None,
        "grant_id": grant.id if grant else None,
    })
    db.commit()
    return {
        "ok": True,
        "is_member": user.is_member,
        "member_type": user.member_type,
        "membership_cycle_id": user.annual_membership_cycle_id,
        "membership_store_id": user.membership_store_id,
        "member_expire_at": user.member_expire_at.isoformat() if user.member_expire_at else None,
        "grant_id": grant.id if grant else None,
    }


@router.post("/users/{user_id}/tags")
def add_user_tag(user_id: int, body: dict, db: Session = Depends(get_db),
                 authorization: str | None = Header(None)):
    """手动打标：body = {"tag_id": 3}"""
    s = _current_staff(authorization, db)
    _require_admin(s)
    _require_store_user(db, user_id, s)
    tag_id = body.get("tag_id")
    if not db.scalar(select(CustomerTag.id).where(
        CustomerTag.id == tag_id,
        CustomerTag.store_id == _staff_store_id(s),
    )):
        raise HTTPException(404, "标签不存在")
    exist = db.scalar(select(CustomerTagRelation).where(
        CustomerTagRelation.user_id == user_id, CustomerTagRelation.tag_id == tag_id
    ))
    if exist:
        return {"ok": True, "msg": "已有此标签"}
    db.add(CustomerTagRelation(user_id=user_id, tag_id=tag_id, source="manual"))
    _audit(db, s, "add_tag", "user", str(user_id), {"tag_id": tag_id})
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/tags/{tag_id}")
def remove_user_tag(user_id: int, tag_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    _require_store_user(db, user_id, s)
    rel = db.scalar(select(CustomerTagRelation).where(
        CustomerTagRelation.user_id == user_id, CustomerTagRelation.tag_id == tag_id
    ))
    if rel:
        db.delete(rel)
        _audit(db, s, "remove_tag", "user", str(user_id), {"tag_id": tag_id})
        db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 7. 用户分群管理
# ──────────────────────────────────────────────────────

@router.get("/segments")
def list_segments(db: Session = Depends(get_db),
                  authorization: str | None = Header(None)) -> list:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    segs = db.execute(select(CustomerSegment).where(
        CustomerSegment.store_id == store_id,
    ).order_by(CustomerSegment.id)).scalars().all()
    return [{
        "id": sg.id, "name": sg.name, "description": sg.description,
        "conditions": sg.conditions, "user_count": sg.user_count,
        "status": sg.status,
    } for sg in segs]


class SegmentIn(BaseModel):
    name: str
    description: str = ""
    conditions: dict = {}


@router.post("/segments")
def create_segment(body: SegmentIn, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    sg = CustomerSegment(store_id=_staff_store_id(s), **body.model_dump())
    db.add(sg)
    _audit(db, s, "create_segment", "segment", body.name)
    db.commit()
    return {"id": sg.id}


@router.post("/segments/{seg_id}")
def update_segment(seg_id: int, body: dict, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    sg = db.scalar(select(CustomerSegment).where(
        CustomerSegment.id == seg_id,
        CustomerSegment.store_id == _staff_store_id(s),
    ))
    if not sg:
        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(sg, k) and k != "id":
            setattr(sg, k, v)
    db.commit()
    return {"ok": True}


@router.post("/segments/{seg_id}/recount")
def recount_segment(seg_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    """重新计算分群人数（实时查询）"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    sg = db.scalar(select(CustomerSegment).where(
        CustomerSegment.id == seg_id,
        CustomerSegment.store_id == _staff_store_id(staff),
    ))
    if not sg:
        raise HTTPException(404)
    # 使用 list_users 同样的逻辑粗略计算
    q = select(User).where(User.id.in_(_store_user_ids(store_id)))
    conds = sg.conditions
    if conds.get("tags"):
        tag_ids_sub = select(CustomerTag.id).where(
            CustomerTag.store_id == store_id,
            CustomerTag.name.in_(conds["tags"]),
        )
        tagged = select(CustomerTagRelation.user_id).where(CustomerTagRelation.tag_id.in_(tag_ids_sub))
        q = q.where(User.id.in_(tagged))
    if conds.get("is_member"):
        q = q.where(User.is_member == True)
    count = db.scalar(select(sa_func.count()).select_from(q.subquery()))
    sg.user_count = count or 0
    db.commit()
    return {"user_count": sg.user_count}


# ──────────────────────────────────────────────────────
# 8. 自动化规则管理
# ──────────────────────────────────────────────────────

@router.get("/automations")
def list_automations(db: Session = Depends(get_db),
                     authorization: str | None = Header(None)) -> list:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    rules = db.execute(select(AutomationRule).where(
        AutomationRule.store_id == store_id,
    ).order_by(AutomationRule.id)).scalars().all()
    return [{
        "id": r.id, "name": r.name, "description": r.description,
        "trigger_event": r.trigger_event, "conditions": r.conditions,
        "actions": r.actions, "is_enabled": r.is_enabled,
        "cooldown_days": r.cooldown_days,
        "trigger_count": r.trigger_count,
        "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
    } for r in rules]


class AutomationIn(BaseModel):
    name: str
    description: str = ""
    trigger_event: str
    conditions: dict | None = None
    actions: list = []
    is_enabled: bool = True
    cooldown_days: int = 0


TRIGGER_EVENTS = [
    {"value": "new_user", "label": "新用户注册"},
    {"value": "first_order", "label": "首单完成"},
    {"value": "order_completed", "label": "服务完成"},
    {"value": "no_visit_30d", "label": "30 天未访问"},
    {"value": "member_expiring", "label": "会员即将到期"},
    {"value": "high_spender", "label": "高客单价（单笔 > 200）"},
]


@router.get("/automations/trigger-events")
def list_trigger_events(db: Session = Depends(get_db),
                        authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _staff_store_id(staff)
    return TRIGGER_EVENTS


@router.post("/automations")
def create_automation(body: AutomationIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = AutomationRule(store_id=_staff_store_id(s), **body.model_dump())
    db.add(r)
    _audit(db, s, "create_automation", "automation", body.name)
    db.commit()
    return {"id": r.id}


@router.post("/automations/{rule_id}")
def update_automation(rule_id: int, body: dict, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = db.scalar(select(AutomationRule).where(
        AutomationRule.id == rule_id,
        AutomationRule.store_id == _staff_store_id(s),
    ))
    if not r:
        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(r, k) and k != "id":
            setattr(r, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/automations/{rule_id}")
def delete_automation(rule_id: int, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = db.scalar(select(AutomationRule).where(
        AutomationRule.id == rule_id,
        AutomationRule.store_id == _staff_store_id(s),
    ))
    if not r:
        raise HTTPException(404)
    db.delete(r)
    db.commit()
    return {"ok": True}



# ──────────────────────────────────────────────────────
# 8.5 房间分配（技师+项目绑定）
# ──────────────────────────────────────────────────────

@router.get("/assignments")
def list_assignments(
    room_id: int | None = Query(None),
    technician_id: int | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> list:
    """查询房间-技师绑定关系"""
    _reject_physical_resource_api()
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    own_room_ids = select(Room.id).where(Room.store_id == store_id)
    own_technician_ids = select(Technician.id).where(Technician.store_id == store_id)
    q = select(RoomAssignment).where(
        RoomAssignment.room_id.in_(own_room_ids),
        RoomAssignment.technician_id.in_(own_technician_ids),
    )
    if room_id:
        q = q.where(RoomAssignment.room_id == room_id)
    if technician_id:
        q = q.where(RoomAssignment.technician_id == technician_id)
    q = q.where(RoomAssignment.is_active == True)
    q = q.order_by(RoomAssignment.id)
    assigns = db.execute(q).scalars().all()
    result = []
    for a in assigns:
        room = db.get(Room, a.room_id)
        tech = db.get(Technician, a.technician_id)
        if not room or not tech:
            continue
        # 获取项目名称和提成
        project_details = []
        for pid in (a.project_ids or []):
            proj = db.get(Project, pid)
            if proj and proj.store_id == store_id:
                comm = a.commission_overrides.get(str(pid), proj.commission_cents) if hasattr(proj, 'commission_cents') else 0
                project_details.append({
                    "id": proj.id, "name": proj.name, "code": proj.code,
                    "commission_cents": comm,
                    "duration_min": proj.duration_min
                })
        result.append({
            "id": a.id, "room_id": a.room_id, "room_name": room.name,
            "technician_id": a.technician_id, "technician_name": tech.name,
            "technician_level": tech.level,
            "project_ids": a.project_ids,
            "project_details": project_details,
            "commission_overrides": a.commission_overrides,
            "is_active": a.is_active,
            "note": a.note,
        })
    return result



# ============================================================
# 8.8 房间操作（开房/服务/结账/打扫/休息/维修）
# ============================================================

VALID_ROOM_STATUSES = [
    "available", "occupied", "in_service", "cleaning", "resting",
    "reserved", "maintenance", "overtime_rest", "inspection",
    "pending_checkout", "off_duty", "booked"
]

VALID_TRANSITIONS = {
    "available": ["occupied", "reserved", "maintenance", "resting"],
    "occupied": ["in_service", "cleaning", "available"],
    "in_service": ["pending_checkout", "inspection"],
    "pending_checkout": ["cleaning", "available"],
    "cleaning": ["available", "inspection"],
    "resting": ["available"],
    "reserved": ["occupied", "available"],
    "maintenance": ["available"],
    "overtime_rest": ["available"],
    "inspection": ["available", "cleaning", "maintenance"],
    "off_duty": ["available"],
    "booked": ["occupied", "available"],
}


class RoomOperateIn(BaseModel):
    action: str  # 目标状态: occupied/in_service/pending_checkout/cleaning/resting/maintenance/available/reserved
    technician_id: int | None = None
    note: str = ""


@router.get("/rooms/stats")
def room_stats(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    """房间统计：各状态数量 + 待结账汇总"""
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    from app.models.operations import Room
    from sqlalchemy import func
    rows = db.execute(
        select(Room.status, Room.operational_status, func.count(Room.id))
        .where(Room.store_id == store_id, Room.is_service_position.is_(True))
        .group_by(Room.status, Room.operational_status)
    ).all()
    stats = {status: 0 for status in VALID_ROOM_STATUSES}
    stats["inactive"] = 0
    stats["total"] = 0
    for status, operational_status, cnt in rows:
        if operational_status == "inactive":
            stats["inactive"] += cnt
        elif status in stats:
            stats[status] = cnt
        stats["total"] += cnt
    # 待结账金额（从 orders 表）
    from app.models import Order
    pending = db.scalar(
        select(func.coalesce(func.sum(Order.pay_amount_cents), 0))
        .where(Order.status == "pending_checkout", Order.store_id == store_id)
    ) or 0
    pending_count = db.scalar(
        select(func.count(Order.id))
        .where(Order.status == "pending_checkout", Order.store_id == store_id)
    ) or 0
    stats["pending_amount_cents"] = pending
    stats["pending_count"] = pending_count
    return stats


@router.post("/rooms/{room_id}/operate")
def operate_room(room_id: int, body: RoomOperateIn,
                 db: Session = Depends(get_db),
                 authorization: str | None = Header(None)):
    """房间状态操作"""
    _reject_physical_resource_api()
    s = _current_staff(authorization, db)
    _require_admin(s)
    from app.models.operations import Room
    room = _require_owned(db.get(Room, room_id), s, "房间不存在")
    if room.is_space_container or not room.is_service_position:
        raise HTTPException(400, "房间是空间容器，请操作房间内的具体床位")
    active_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == room.id,
    ))
    if active_occupancy:
        raise HTTPException(409, "当前服务位已有活动占用，请在服务位看板完成现场操作")
    target = body.action
    if target not in VALID_TRANSITIONS.get(room.status, []):
        raise HTTPException(400, f"当前状态 {room.status} 不能直接变为 {target}")
    old_status = room.status
    room.status = target
    if target == "occupied" and body.technician_id:
        from app.models.operations import Technician
        tech = db.get(Technician, body.technician_id)
        if tech and tech.store_id == room.store_id:
            room.current_tech = tech.name
            room.used_count = 1
        else:
            raise HTTPException(404, "技师不存在")
    if target == "in_service":
        room.used_count = max(room.used_count or 0, 1)
    if target in ("available", "cleaning"):
        room.used_count = 0
        room.current_tech = ""
    if body.note:
        room.note = body.note
    _audit(db, s, "room_operate", "room", str(room_id), {
        "from_status": old_status,
        "to_status": target,
        "technician_id": body.technician_id,
    })
    db.commit()
    return {"id": room.id, "code": room.code, "status": room.status, "old_status": old_status}


@router.get("/rooms/pending-checkout")
def pending_checkout_orders(db: Session = Depends(get_db),
                            authorization: str | None = Header(None)):
    """待结账订单列表"""
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    from app.models import Order
    orders = db.execute(
        select(Order).where(
            Order.status == "pending_checkout",
            Order.store_id == store_id,
        )
        .order_by(Order.created_at.desc()).limit(20)
    ).scalars().all()
    return [{
        "id": o.id,
        "order_no": o.order_no,
        "items": o.items,
        "pay_amount_cents": o.pay_amount_cents,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    } for o in orders]


class AssignmentIn(BaseModel):
    room_id: int
    technician_id: int
    project_ids: list = []
    commission_overrides: dict = {}
    note: str = ""


@router.post("/assignments")
def create_assignment(body: AssignmentIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    """为房间绑定技师和项目"""
    _reject_physical_resource_api()
    s = _current_staff(authorization, db)
    _require_admin(s)
    _staff_store_id(s)
    room = _require_owned(db.get(Room, body.room_id), s, "房间不存在")
    tech = _require_owned(db.get(Technician, body.technician_id), s, "技师不存在")
    if room.store_id != tech.store_id:
        raise HTTPException(400, "房间与技师不属于同一门店")
    for project_id in body.project_ids:
        _require_owned(db.get(Project, project_id), s, "项目不存在")
    # 检查是否已有相同绑定
    exist = db.scalar(select(RoomAssignment).where(
        RoomAssignment.room_id == body.room_id,
        RoomAssignment.technician_id == body.technician_id,
        RoomAssignment.is_active == True,
    ))
    if exist:
        # 更新现有绑定
        exist.project_ids = body.project_ids
        exist.commission_overrides = body.commission_overrides
        exist.note = body.note
        _audit(db, s, "update_assignment", "assignment", str(exist.id))
        db.commit()
        return {"id": exist.id, "updated": True}
    a = RoomAssignment(**body.model_dump())
    db.add(a)
    _audit(db, s, "create_assignment", "assignment", f"room_{body.room_id}_tech_{body.technician_id}")
    db.commit()
    return {"id": a.id}


@router.delete("/assignments/{assign_id}")
def delete_assignment(assign_id: int, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    """移除房间绑定（软删除）"""
    _reject_physical_resource_api()
    s = _current_staff(authorization, db)
    _require_admin(s)
    a = db.get(RoomAssignment, assign_id)
    if not a:
        raise HTTPException(404, "绑定不存在")
    _require_owned(db.get(Room, a.room_id), s, "绑定不存在")
    a.is_active = False
    _audit(db, s, "delete_assignment", "assignment", str(assign_id))
    db.commit()
    return {"ok": True}


@router.get("/assignments/room/{room_id}")
def get_room_detail(room_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    """获取房间详情：含绑定的技师和项目"""
    _reject_physical_resource_api()
    staff = _current_staff(authorization, db)
    room = _require_owned(db.get(Room, room_id), staff, "房间不存在")
    assigns = db.execute(
        select(RoomAssignment).where(
            RoomAssignment.room_id == room_id,
            RoomAssignment.is_active == True,
        )
    ).scalars().all()
    technicians = []
    for a in assigns:
        tech = db.get(Technician, a.technician_id)
        if tech:
            proj_details = []
            for pid in (a.project_ids or []):
                proj = db.get(Project, pid)
                if proj and proj.store_id == room.store_id:
                    comm = a.commission_overrides.get(str(pid), proj.commission_cents if hasattr(proj, 'commission_cents') else 0)
                    proj_details.append({
                        "id": proj.id, "name": proj.name, "code": proj.code,
                        "commission_cents": comm,
                    })
            technicians.append({
                "id": tech.id, "name": tech.name, "level": tech.level,
                "projects": proj_details,
                "commission_rules": tech.commission_rules,
                "default_commission_rate": tech.default_commission_rate,
                "assignment_id": a.id,
            })
    return {
        "id": room.id, "name": room.name, "code": room.code,
        "room_type": room.room_type, "status": room.status,
        "technicians": technicians,
    }


# ──────────────────────────────────────────────────────
# 9. 仪表盘（聚合概览）
# ──────────────────────────────────────────────────────

@router.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    store_user_ids = select(Order.user_id).where(Order.store_id == store_id).distinct()
    total_users = db.scalar(select(sa_func.count()).select_from(User).where(User.id.in_(store_user_ids)))
    total_members = db.scalar(select(sa_func.count()).select_from(User).where(
        User.id.in_(store_user_ids), User.is_member == True,
    ))
    total_orders = db.scalar(select(sa_func.count()).select_from(Order).where(Order.store_id == store_id))
    total_rooms = db.scalar(select(sa_func.count()).select_from(Room).where(Room.store_id == store_id))
    total_techs = db.scalar(select(sa_func.count()).select_from(Technician).where(Technician.store_id == store_id))
    total_tags = db.scalar(select(sa_func.count()).select_from(CustomerTag))
    total_segments = db.scalar(select(sa_func.count()).select_from(CustomerSegment))
    total_automations = db.scalar(select(sa_func.count()).select_from(AutomationRule))
    return {
        "total_users": total_users, "total_members": total_members,
        "total_orders": total_orders, "total_rooms": total_rooms,
        "total_techs": total_techs, "total_tags": total_tags,
        "total_segments": total_segments, "total_automations": total_automations,
    }
