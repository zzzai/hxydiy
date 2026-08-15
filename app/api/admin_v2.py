"""管理后台 V2：房间/技师/项目/商品/标签/分层/自动化 — 完整 CRUD

权限：admin 可读写，staff 只读。所有写操作记录 AuditLog。
"""

from datetime import UTC, datetime, timezone
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import delete, select, func as sa_func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff
from app.db.session import get_db
from app.models import (
    CouponTemplate, UserCoupon, MemberPlan, Recharge,
    Project, PriceBook, Addon, Product, Store, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, ServiceLine, PageContent,
    EventLog, Order, OrderEvent, User, AuditLog, Staff, PositionOccupancy,
    MembershipBenefitGrant,
    ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup,
)
from app.domain.catalog_options import CatalogDomainError, copy_catalog_version_graph, lock_catalog_projects
from app.domain.occupancy import audit_occupancy, release_occupancy
from app.models.operations import Room, Technician
from app.models.room_assign import RoomAssignment
from app.models.scrm import (
    CustomerTag, CustomerTagRelation, CustomerSegment,
    AutomationRule, AutomationLog,
)

router = APIRouter(prefix="/admin/v2", tags=["admin-v2"])


# ─── helpers ─────────────────────────────────────────

def _require_admin(staff: Staff):
    if staff.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


def _staff_store_id(staff: Staff) -> int:
    if not staff.store_id:
        raise HTTPException(status_code=403, detail="当前账号未绑定门店")
    return staff.store_id


def _scoped_store_id(staff: Staff, requested_store_id: int | None = None) -> int:
    store_id = _staff_store_id(staff)
    if requested_store_id is not None and requested_store_id != store_id:
        raise HTTPException(status_code=403, detail="无权访问其他门店数据")
    return store_id


def _require_owned(entity, staff: Staff, not_found_detail: str):
    if not entity or entity.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail=not_found_detail)
    return entity


def _store_user_ids(store_id: int):
    """门店顾客：有本店订单的用户 ∪ 有本店选单的 DIY 顾客。"""
    order_users = select(Order.user_id).where(Order.store_id == store_id)
    selection_users = select(SelectionSession.customer_id).where(
        SelectionSession.store_id == store_id,
        SelectionSession.customer_id.is_not(None),
    )
    return order_users.union(selection_users)


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


def _audit(db: Session, actor: str, action: str, entity: str, eid: str, detail: dict = None):
    db.add(AuditLog(
        actor_type="staff", actor_id=actor, action=action,
        entity_type=entity, entity_id=eid, detail=detail or {},
    ))


Paginated = dict  # { items, total, page, page_size }


class PageContentIn(BaseModel):
    title: str = "到店选项目"
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
    _audit(db, staff.name, "update_page_content", "page_content", f"{store_id}:{page_key}")
    db.commit()
    db.refresh(content)
    return _page_content_view(content)

# ──────────────────────────────────────────────────────
# 0. 到店选项目：独立于订单的顾客 DIY 需求
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
            "nickname": customer.nickname,
            "phone": customer.phone,
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
    session = _owned_selection(db, session_id, staff)
    if session.status == "confirmed":
        return _selection_view(session, db.get(User, session.customer_id) if session.customer_id else None)
    if session.status != "submitted":
        raise HTTPException(status_code=409, detail="只有已提交选单可以确认")
    revision = db.scalar(select(SelectionRevision).where(
        SelectionRevision.selection_session_id == session.id,
        SelectionRevision.state == "submitted",
    ).order_by(SelectionRevision.revision_no.desc()))
    confirmed_at = datetime.now(timezone.utc)
    confirmed_items = []
    if revision:
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
    else:
        # 简化提交路径尚未创建 revision；仍以确认后的独立选单行计价，不能把顾客提交当作已确认服务。
        confirmed_items = [{**item, "state": "confirmed"} for item in session.items or []]

    # 泡脚组合优惠只取前台确认的独立服务单位；确认后立即刷新冻结报价。
    session.items = confirmed_items
    from app.api.selections import refresh_session_pricing
    pricing = refresh_session_pricing(db, session, confirmed_at=confirmed_at)
    if revision:
        revision.snapshot = {
            **(revision.snapshot or {}),
            "items": confirmed_items,
            "pricing": pricing,
        }
    session.status = "confirmed"
    session.confirmed_at = confirmed_at
    _audit(db, staff.name, "confirm_selection", "selection_session", session.id)
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
    _audit(db, staff.name, "cancel_selection", "selection_session", session.id)
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
    change = db.get(SelectionChangeRequest, request_id)
    if not change:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    session = _owned_selection(db, change.selection_session_id, staff)
    if change.state == "approved":
        lines = db.query(ServiceLine).filter(ServiceLine.selection_revision_id == change.selection_revision_id).all()
        return {"id": change.id, "state": change.state, "service_lines": [_service_line_view(line) for line in lines]}
    if change.state != "awaiting_staff_confirmation":
        raise HTTPException(status_code=409, detail="当前加选请求不能确认")
    revision = db.get(SelectionRevision, change.selection_revision_id)
    if not revision or revision.selection_session_id != session.id:
        raise HTTPException(status_code=409, detail="加选版本不存在")
    occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.selection_session_id == session.id,
    ).order_by(PositionOccupancy.id.desc()))
    if not occupancy or occupancy.status != "in_service":
        raise HTTPException(status_code=409, detail="服务已结束，当前加选不能确认")
    lines = []
    for item in (revision.snapshot or {}).get("added_items", []):
        line = ServiceLine(
            id=str(uuid.uuid4()),
            selection_session_id=session.id,
            selection_revision_id=revision.id,
            snapshot=item,
            state="pending",
        )
        db.add(line)
        lines.append(line)
    snapshot = revision.snapshot or {}
    pricing = snapshot.get("pricing") or {}
    session.items = snapshot.get("items", session.items or [])
    session.diy_preferences = snapshot.get("diy_preferences", session.diy_preferences or {})
    session.pricing_snapshot = pricing
    session.store_total_cents = int(pricing.get("store_total_cents", session.store_total_cents) or 0)
    session.member_total_cents = int(pricing.get("member_total_cents", session.member_total_cents) or 0)
    session.status = "confirmed"
    session.confirmed_at = session.confirmed_at or datetime.now(timezone.utc)
    change.state = "approved"
    change.resolved_at = datetime.now(timezone.utc)
    change.resolved_by_staff_id = staff.id
    revision.state = "confirmed"
    revision.confirmed_at = datetime.now(timezone.utc)
    revision.confirmed_by_staff_id = staff.id
    _audit(db, staff.name, "approve_selection_change", "selection_change_request", change.id, {
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
    change = db.get(SelectionChangeRequest, request_id)
    if not change:
        raise HTTPException(status_code=404, detail="加选请求不存在")
    session = _owned_selection(db, change.selection_session_id, staff)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="拒绝加选必须填写原因")
    if change.state == "rejected":
        return {"id": change.id, "state": change.state, "reason": change.reason}
    if change.state != "awaiting_staff_confirmation":
        raise HTTPException(status_code=409, detail="当前加选请求不能拒绝")
    revision = db.get(SelectionRevision, change.selection_revision_id)
    if not revision or revision.selection_session_id != session.id:
        raise HTTPException(status_code=409, detail="加选版本不存在")
    change.state = "rejected"
    change.reason = reason
    change.resolved_at = datetime.now(timezone.utc)
    change.resolved_by_staff_id = staff.id
    revision.state = "rejected"
    _audit(db, staff.name, "reject_selection_change", "selection_change_request", change.id, {
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
    return {"items": [{
        "id": r.id, "store_id": r.store_id, "code": r.code, "name": r.name,
        "room_type": r.room_type, "floor": r.floor, "capacity": r.capacity,
        "room_group": r.room_group, "used_count": r.used_count,
        "current_tech": r.current_tech,
        "status": r.status, "note": r.note, "sort_order": r.sort_order,
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
    r = Room(**body.model_dump())
    db.add(r)
    _audit(db, s.name, "create_room", "room", body.code)
    db.commit()
    return {"id": r.id, "code": r.code}


@router.post("/rooms/{room_id}")
def update_room(room_id: int, body: dict, db: Session = Depends(get_db),
                authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = _require_owned(db.get(Room, room_id), s, "房间不存在")
    active_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == r.id,
    ))
    if active_occupancy:
        raise HTTPException(409, "当前服务位已有活动占用，请在服务位看板完成现场操作")
    runtime_fields = {"status", "used_count", "current_tech", "version"}
    if runtime_fields.intersection(body):
        raise HTTPException(400, "房态和服务信息请使用房态操作或服务位看板更新")
    for k, v in body.items():
        if hasattr(r, k) and k not in {"id", "store_id", *runtime_fields}:
            setattr(r, k, v)
    _audit(db, s.name, "update_room", "room", str(room_id))
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
    _audit(db, s.name, "delete_room", "room", str(room_id))
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
    return {"items": [{
        "id": t.id, "store_id": t.store_id, "code": t.code, "name": t.name,
        "phone": t.phone, "avatar_url": t.avatar_url, "gender": t.gender,
        "level": t.level, "skills": t.skills, "intro": t.intro,
        "commission_rules": t.commission_rules,
        "default_commission_rate": t.default_commission_rate,
        "status": t.status, "sort_order": t.sort_order,
        "hire_date": t.hire_date.isoformat() if t.hire_date else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in items], "total": total, "page": page, "page_size": page_size}


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
    _audit(db, s.name, "create_tech", "technician", body.code)
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
    _audit(db, s.name, "update_tech", "technician", str(tech_id))
    db.commit()
    return {"ok": True}


@router.delete("/technicians/{tech_id}")
def delete_technician(tech_id: int, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    t = _require_owned(db.get(Technician, tech_id), s, "技师不存在")
    db.delete(t)
    _audit(db, s.name, "delete_tech", "technician", str(tech_id))
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 3. 项目管理（管理端 CRUD + 价格表同步）
# ──────────────────────────────────────────────────────

@router.get("/projects")
def list_projects_admin(
    store_id: int | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> list:
    staff = _current_staff(authorization, db)
    scoped_store_id = _scoped_store_id(staff, store_id)
    q = select(Project).where(Project.store_id == scoped_store_id)
    if status:
        q = q.where(Project.publication_status == status)
    q = q.order_by(Project.id)
    projects = db.execute(q).scalars().all()
    result = []
    for p in projects:
        prices = db.execute(
            select(PriceBook)
            .where(PriceBook.project_id == p.id)
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
    return result


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
    if project is None or project.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="项目不存在")
    referrers = _published_catalog_referrer_ids(db, project_id)
    return project, referrers


def _append_project_prices(db: Session, project_id: int, prices: dict[ProjectPriceType, int], publisher: str) -> None:
    for price_type, amount_cents in prices.items():
        db.add(PriceBook(
            project_id=project_id,
            price_type=price_type,
            amount_cents=amount_cents,
            publisher=publisher,
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
    _require_admin(staff)
    _scoped_store_id(staff, body.store_id)
    data = body.model_dump(exclude={"prices"})
    project = Project(**data)
    db.add(project)
    db.flush()
    _append_project_prices(db, project.id, body.prices, staff.name)
    _audit(db, staff.name, "create_project", "project", project.code)
    _commit_project_or_conflict(db)
    return {"id": project.id, "code": project.code}


def _update_project_strict(project_id: int, body: ProjectPatch, db: Session, staff: Staff) -> dict:
    project, referrers = _locked_project_for_update(db, project_id, staff)
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
    _audit(db, staff.name, "update_project", "project", str(project.id))
    _commit_project_or_conflict(db)
    return {"ok": True, "id": project.id, "code": project.code, "publication_status": project.publication_status}


@router.patch("/projects/{proj_id}")
def patch_project(proj_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                  authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    return _update_project_strict(proj_id, body, db, staff)


@router.post("/projects/{proj_id}")
def update_project(proj_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    """保留旧 POST 路径，但使用与 PATCH 完全相同的严格契约。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    return _update_project_strict(proj_id, body, db, staff)


@router.post("/projects/{proj_id}/duplicate")
def duplicate_project(proj_id: int, body: ProjectDuplicateIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
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
        .where(PriceBook.project_id == source.id)
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
    _audit(db, staff.name, "duplicate_project", "project", str(source.id), {"duplicate_project_id": duplicate.id})
    _commit_project_or_conflict(db)
    return {"id": duplicate.id, "code": duplicate.code, "catalog_version_id": draft.id}


@router.post("/projects/{proj_id}/archive")
def archive_project(proj_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
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


def _validate_addon_payload(db: Session, body: AddonIn, store_id: int) -> None:
    if body.publication_status not in {"draft", "candidate", "published", "archived"}:
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


def _addon_view(addon: Addon) -> dict:
    store_price = int(addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents)
    member_price = int(
        addon.member_price_cents
        if addon.member_price_enabled and addon.member_price_cents is not None
        else store_price
    )
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
        "member_price_cents": member_price,
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
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> list[dict]:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    scoped_store_id = _scoped_store_id(staff, store_id)
    stmt = select(Addon).where(Addon.store_id == scoped_store_id)
    if status:
        stmt = stmt.where(Addon.publication_status == status)
    if parent_project_id is not None:
        stmt = stmt.where(Addon.parent_project_id == parent_project_id)
    return [_addon_view(addon) for addon in db.scalars(stmt.order_by(Addon.display_order, Addon.id))]


@router.post("/addons")
def create_addon(body: AddonIn, db: Session = Depends(get_db), authorization: str | None = Header(None)) -> dict:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _scoped_store_id(staff, body.store_id)
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
    _audit(db, staff.name, "create_addon", "addon", str(addon.id), {"code": addon.code})
    db.commit()
    db.refresh(addon)
    return _addon_view(addon)


@router.post("/addons/{addon_id}")
def update_addon(addon_id: int, body: AddonPatchIn, db: Session = Depends(get_db), authorization: str | None = Header(None)) -> dict:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    addon = _require_owned(db.get(Addon, addon_id), staff, "加项不存在")
    current = _addon_view(addon)
    merged = AddonIn(
        store_id=addon.store_id,
        code=body.code if body.code is not None else addon.code,
        name=body.name if body.name is not None else addon.name,
        parent_project_id=body.parent_project_id if body.parent_project_id is not None else addon.parent_project_id,
        duration_min=body.duration_min if body.duration_min is not None else addon.duration_min,
        summary=body.summary if body.summary is not None else addon.summary,
        image_url=body.image_url if body.image_url is not None else addon.image_url,
        display_order=body.display_order if body.display_order is not None else addon.display_order,
        chargeable=body.chargeable if body.chargeable is not None else addon.chargeable,
        store_price_cents=body.store_price_cents if body.store_price_cents is not None else current["store_price_cents"],
        member_price_cents=body.member_price_cents if body.member_price_cents is not None else (
            addon.member_price_cents if addon.member_price_enabled else None
        ),
        member_price_enabled=body.member_price_enabled if body.member_price_enabled is not None else addon.member_price_enabled,
        independently_sellable=body.independently_sellable if body.independently_sellable is not None else addon.independently_sellable,
        can_attach_to_parent=body.can_attach_to_parent if body.can_attach_to_parent is not None else addon.can_attach_to_parent,
        publication_status=body.publication_status if body.publication_status is not None else addon.publication_status,
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
    _audit(db, staff.name, "update_addon", "addon", str(addon.id))
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
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> list:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    scoped_store_id = _scoped_store_id(staff, store_id)
    q = select(Product).where(Product.store_id == scoped_store_id)
    if status:
        q = q.where(Product.publication_status == status)
    q = q.order_by(Product.id)
    products = db.execute(q).scalars().all()
    return [{
        "id": p.id, "store_id": p.store_id, "code": p.code, "name": p.name,
        "desc": p.desc, "spec": p.spec, "product_type": p.product_type,
        "price_cents": p.price_cents, "image_url": p.image_url,
        "publication_status": p.publication_status,
    } for p in products]


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


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    _scoped_store_id(s, body.store_id)
    p = Product(**body.model_dump())
    db.add(p)
    _audit(db, s.name, "create_product", "product", body.code)
    db.commit()
    return {"id": p.id, "code": p.code}


@router.post("/products/{prod_id}")
def update_product(prod_id: int, body: dict, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    p = _require_owned(db.get(Product, prod_id), s, "商品不存在")
    for k, v in body.items():
        if hasattr(p, k) and k not in {"id", "store_id"}:
            setattr(p, k, v)
    _audit(db, s.name, "update_product", "product", str(prod_id))
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 5. 用户标签管理
# ──────────────────────────────────────────────────────

@router.get("/tags")
def list_tags(db: Session = Depends(get_db),
              authorization: str | None = Header(None)) -> list:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    tags = db.execute(select(CustomerTag).order_by(CustomerTag.id)).scalars().all()
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


@router.post("/tags")
def create_tag(body: TagIn, db: Session = Depends(get_db),
               authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    if db.scalar(select(CustomerTag).where(CustomerTag.name == body.name)):
        raise HTTPException(400, "标签名已存在")
    t = CustomerTag(**body.model_dump())
    db.add(t)
    _audit(db, s.name, "create_tag", "tag", body.name)
    db.commit()
    return {"id": t.id}


@router.post("/tags/{tag_id}")
def update_tag(tag_id: int, body: dict, db: Session = Depends(get_db),
               authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    t = db.get(CustomerTag, tag_id)
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
    t = db.get(CustomerTag, tag_id)
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
        sub = select(CustomerTagRelation.user_id).where(CustomerTagRelation.tag_id == tag_id)
        q = q.where(User.id.in_(sub))
    if segment_id:
        seg = db.get(CustomerSegment, segment_id)
        if seg and seg.conditions:
            conds = seg.conditions
            if "tags" in conds:
                tag_names = conds["tags"]
                tag_ids_sub = select(CustomerTag.id).where(CustomerTag.name.in_(tag_names))
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
        q = q.where(User.nickname.ilike(f"%{search}%"))
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
            "id": u.id, "nickname": u.nickname or f"用户{u.id}",
            "phone_tail": u.phone[-4:] if u.phone else "",
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

    # 会员身份变化后，重算该顾客未完结选单的计价快照（draft/submitted）。
    from app.api.selections import refresh_session_pricing
    open_sessions = db.scalars(select(SelectionSession).where(
        SelectionSession.customer_id == user_id,
        SelectionSession.status.in_(["draft", "submitted"]),
    ))
    for session in open_sessions:
        refresh_session_pricing(db, session)
    _audit(db, staff.name, "set_membership", "user", str(user_id), {
        "is_member": user.is_member,
        "previous": previous,
        "previous_member_type": previous_member_type,
        "member_type": user.member_type,
        "membership_cycle_id": user.annual_membership_cycle_id,
        "member_expire_at": user.member_expire_at.isoformat() if user.member_expire_at else None,
        "grant_id": grant.id if grant else None,
    })
    db.commit()
    return {
        "ok": True,
        "is_member": user.is_member,
        "member_type": user.member_type,
        "membership_cycle_id": user.annual_membership_cycle_id,
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
    exist = db.scalar(select(CustomerTagRelation).where(
        CustomerTagRelation.user_id == user_id, CustomerTagRelation.tag_id == tag_id
    ))
    if exist:
        return {"ok": True, "msg": "已有此标签"}
    db.add(CustomerTagRelation(user_id=user_id, tag_id=tag_id, source="manual"))
    _audit(db, s.name, "add_tag", "user", str(user_id), {"tag_id": tag_id})
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
        _audit(db, s.name, "remove_tag", "user", str(user_id), {"tag_id": tag_id})
        db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────
# 7. 用户分群管理
# ──────────────────────────────────────────────────────

@router.get("/segments")
def list_segments(db: Session = Depends(get_db),
                  authorization: str | None = Header(None)) -> list:
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    segs = db.execute(select(CustomerSegment).order_by(CustomerSegment.id)).scalars().all()
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
    sg = CustomerSegment(**body.model_dump())
    db.add(sg)
    _audit(db, s.name, "create_segment", "segment", body.name)
    db.commit()
    return {"id": sg.id}


@router.post("/segments/{seg_id}")
def update_segment(seg_id: int, body: dict, db: Session = Depends(get_db),
                   authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    sg = db.get(CustomerSegment, seg_id)
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
    sg = db.get(CustomerSegment, seg_id)
    if not sg:
        raise HTTPException(404)
    # 使用 list_users 同样的逻辑粗略计算
    q = select(User).where(User.id.in_(_store_user_ids(store_id)))
    conds = sg.conditions
    if conds.get("tags"):
        tag_ids_sub = select(CustomerTag.id).where(CustomerTag.name.in_(conds["tags"]))
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
    _require_admin(staff)
    rules = db.execute(select(AutomationRule).order_by(AutomationRule.id)).scalars().all()
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
    _require_admin(staff)
    return TRIGGER_EVENTS


@router.post("/automations")
def create_automation(body: AutomationIn, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = AutomationRule(**body.model_dump())
    db.add(r)
    _audit(db, s.name, "create_automation", "automation", body.name)
    db.commit()
    return {"id": r.id}


@router.post("/automations/{rule_id}")
def update_automation(rule_id: int, body: dict, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    s = _current_staff(authorization, db)
    _require_admin(s)
    r = db.get(AutomationRule, rule_id)
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
    r = db.get(AutomationRule, rule_id)
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
        select(Room.status, func.count(Room.id))
        .where(Room.store_id == store_id)
        .group_by(Room.status)
    ).all()
    stats = {status: 0 for status in VALID_ROOM_STATUSES}
    stats["total"] = 0
    for status, cnt in rows:
        if status in stats:
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
    s = _current_staff(authorization, db)
    _require_admin(s)
    from app.models.operations import Room
    room = _require_owned(db.get(Room, room_id), s, "房间不存在")
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
    _audit(db, s.name, "room_operate", "room", str(room_id), {
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
        _audit(db, s.name, "update_assignment", "assignment", str(exist.id))
        db.commit()
        return {"id": exist.id, "updated": True}
    a = RoomAssignment(**body.model_dump())
    db.add(a)
    _audit(db, s.name, "create_assignment", "assignment", f"room_{body.room_id}_tech_{body.technician_id}")
    db.commit()
    return {"id": a.id}


@router.delete("/assignments/{assign_id}")
def delete_assignment(assign_id: int, db: Session = Depends(get_db),
                      authorization: str | None = Header(None)):
    """移除房间绑定（软删除）"""
    s = _current_staff(authorization, db)
    _require_admin(s)
    a = db.get(RoomAssignment, assign_id)
    if not a:
        raise HTTPException(404, "绑定不存在")
    _require_owned(db.get(Room, a.room_id), s, "绑定不存在")
    a.is_active = False
    _audit(db, s.name, "delete_assignment", "assignment", str(assign_id))
    db.commit()
    return {"ok": True}


@router.get("/assignments/room/{room_id}")
def get_room_detail(room_id: int, db: Session = Depends(get_db),
                    authorization: str | None = Header(None)):
    """获取房间详情：含绑定的技师和项目"""
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
