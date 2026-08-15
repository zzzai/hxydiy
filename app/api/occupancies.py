"""扫码入口、服务位平面图和门店占用动作 API。"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, _staff_store_id
from app.core.config import settings
from app.db.session import get_db
from app.domain.occupancy import (
    HOLD_TTL_MINUTES,
    aware,
    audit_occupancy,
    expire_stale_holds,
    occupancy_view,
    position_view,
    release_occupancy,
    utcnow,
)
from app.models import BrowserInstance, PositionOccupancy, Room, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceLine, Store, User
from app.models.service import ServiceOrder, Visit
from app.schemas.occupancy import EntrySessionIn, KioskSessionIn, MoveOccupancyIn, OccupancyActionIn
from app.schemas.selection import SelectionSessionOut


router = APIRouter(tags=["service-position-occupancy"])


def _selection_view(session: SelectionSession) -> dict:
    return SelectionSessionOut.model_validate(session).model_dump()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


ANONYMOUS_COOKIE = "hxy_browser_token"


def _browser_customer(db: Session, request: Request | None) -> tuple[int, str, bool]:
    """读取或创建匿名顾客；凭证只通过 HttpOnly Cookie 传递。"""
    token = request.cookies.get(ANONYMOUS_COOKIE) if request else None
    if token:
        browser = db.scalar(select(BrowserInstance).where(BrowserInstance.token_hash == _hash_token(token)))
        if browser:
            browser.last_seen_at = utcnow()
            return browser.customer_id, token, True
    token = secrets.token_urlsafe(32)
    anonymous = User(openid=f"anon_{uuid.uuid4().hex}")
    db.add(anonymous)
    db.flush()
    db.add(BrowserInstance(token_hash=_hash_token(token), customer_id=anonymous.id))
    return anonymous.id, token, False


def _verify_selection_token(session: SelectionSession, access_token: str | None) -> None:
    if not access_token or not secrets.compare_digest(session.access_token_hash, _hash_token(access_token)):
        raise HTTPException(status_code=403, detail="选单访问凭证无效")


def _active_occupancy_for_room(db: Session, room_id: int) -> PositionOccupancy | None:
    return db.scalar(select(PositionOccupancy).where(PositionOccupancy.active_room_id == room_id))


def _create_entry(db: Session, body: EntrySessionIn, request: Request) -> tuple[SelectionSession, PositionOccupancy, Room, str, bool, str]:
    expire_stale_holds(db, body.store_id)
    store = db.get(Store, body.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    room = db.scalar(select(Room).where(
        Room.store_id == body.store_id,
        Room.code == body.position_code,
    ).with_for_update())
    if not room or room.operational_status != "active":
        raise HTTPException(status_code=404, detail="服务位不存在或暂不可用")
    anonymous_customer_id, browser_token, _ = _browser_customer(db, request)
    browser_occupancy = db.scalar(
        select(PositionOccupancy)
        .join(SelectionSession, SelectionSession.id == PositionOccupancy.active_session_id)
        .where(
            PositionOccupancy.store_id == body.store_id,
            PositionOccupancy.active_room_id.is_not(None),
            SelectionSession.customer_id == anonymous_customer_id,
        )
    )
    if browser_occupancy and browser_occupancy.active_room_id != room.id:
        current_room = db.get(Room, browser_occupancy.active_room_id)
        raise HTTPException(status_code=409, detail={
            "code": "BROWSER_ACTIVE_ELSEWHERE",
            "message": f"当前设备已绑定{current_room.customer_label if current_room else '其他服务位'}，请核对二维码或联系前台",
            "current_position_code": current_room.code if current_room else None,
        })
    existing = _active_occupancy_for_room(db, room.id)
    if existing:
        existing_session = db.get(SelectionSession, existing.active_session_id)
        if existing_session and existing_session.customer_id == anonymous_customer_id and existing_session.status in {"draft", "submitted", "confirmed"}:
            # 旋转访问凭证，允许本浏览器在 localStorage 丢失后安全恢复自己的选单。
            token = secrets.token_urlsafe(32)
            existing_session.access_token_hash = _hash_token(token)
            db.commit()
            db.refresh(existing_session)
            return existing_session, existing, room, token, True, browser_token
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_OCCUPIED",
            "message": "该服务位已有顾客，请核对二维码或联系前台",
            "position_code": room.code,
            "state": existing.status,
        })
    if room.status != "available":
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_UNAVAILABLE",
            "message": "该服务位暂不可用，请联系前台安排",
            "position_code": room.code,
            "state": room.status,
        })

    now = utcnow()
    token = secrets.token_urlsafe(32)
    session = SelectionSession(
        id=str(uuid.uuid4()),
        access_token_hash=_hash_token(token),
        store_id=body.store_id,
        customer_id=anonymous_customer_id,
        source=body.source,
        device_label=body.device_label,
        status="draft",
        items=[],
        diy_preferences={},
        pricing_snapshot={},
        expires_at=now + timedelta(hours=12),
    )
    db.add(session)
    db.flush()
    occupancy = PositionOccupancy(
        store_id=body.store_id,
        room_id=room.id,
        active_room_id=room.id,
        selection_session_id=session.id,
        active_session_id=session.id,
        status="held",
        source=body.source,
        hold_expires_at=now + timedelta(minutes=HOLD_TTL_MINUTES),
    )
    db.add(occupancy)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_OCCUPIED",
            "message": "该服务位刚刚被其他顾客使用，请联系前台",
            "position_code": room.code,
        }) from exc
    audit_occupancy(db, occupancy, "position_hold_created", "customer", session.id, {
        "room_id": room.id,
        "position_code": room.code,
        "source": body.source,
    })
    db.commit()
    db.refresh(session)
    db.refresh(occupancy)
    return session, occupancy, room, token, False, browser_token


@router.post("/entry-sessions")
def create_entry_session(body: EntrySessionIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    if body.source == "kiosk":
        raise HTTPException(status_code=403, detail={
            "code": "KIOSK_REQUIRES_STAFF_BINDING",
            "message": "共享 iPad 必须由前台先绑定服务位",
        })
    session, occupancy, room, token, resumed, browser_token = _create_entry(db, body, request)
    response.set_cookie(
        ANONYMOUS_COOKIE,
        browser_token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=60 * 60 * 24 * 365 * 2,
        path="/",
    )
    return {
        "session": _selection_view(session),
        "occupancy": occupancy_view(occupancy),
        "position": position_view(room, occupancy, current=True),
        "access_token": token,
        "resumed": resumed,
    }


@router.get("/stores/{store_id}/service-position-map")
def customer_position_map(
    store_id: int,
    session_id: str | None = Query(default=None),
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    expire_stale_holds(db, store_id)
    current_occupancy = None
    if session_id:
        session = db.get(SelectionSession, session_id)
        if session and session.store_id == store_id:
            _verify_selection_token(session, x_selection_token)
            current_occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.active_session_id == session_id,
            ))
    rooms = list(db.scalars(select(Room).where(
        Room.store_id == store_id,
        Room.room_type == "sofa",
        Room.customer_selectable.is_(True),
    ).order_by(Room.sort_order, Room.id)))
    # 房间不进入公共平面图；仅向已验证的当前房间会话追加“当前房间”，
    # 便于刷新恢复，同时不暴露其他房间编号或选择入口。
    if current_occupancy:
        current_room = db.get(Room, current_occupancy.active_room_id)
        if current_room and current_room.room_type == "room":
            rooms.append(current_room)
    occupancies = {
        item.active_room_id: item
        for item in db.scalars(select(PositionOccupancy).where(
            PositionOccupancy.store_id == store_id,
            PositionOccupancy.active_room_id.is_not(None),
        ))
    }
    return {
        "store_id": store_id,
        "positions": [position_view(
            room,
            occupancies.get(room.id),
            current=bool(current_occupancy and current_occupancy.active_room_id == room.id),
        ) for room in rooms],
    }


@router.post("/occupancies/{occupancy_id}/move")
def customer_move_occupancy(
    occupancy_id: int,
    body: MoveOccupancyIn,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    occupancy = db.get(PositionOccupancy, occupancy_id)
    if not occupancy or not occupancy.active_room_id:
        raise HTTPException(status_code=404, detail="活动占用不存在")
    session = db.get(SelectionSession, occupancy.selection_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="选单不存在")
    _verify_selection_token(session, x_selection_token)
    current_room = db.get(Room, occupancy.active_room_id)
    if occupancy.source == "kiosk" or (current_room and current_room.room_type == "room"):
        raise HTTPException(status_code=403, detail={
            "code": "POSITION_LOCKED",
            "message": "当前服务位已由前台或房间二维码绑定，请联系工作人员调整",
        })
    if occupancy.status != "held":
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_LOCKED",
            "message": "选单已提交，请联系前台调整服务位",
        })
    if body.version is not None and body.version != occupancy.version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT", "message": "服务位状态已变化，请刷新"})
    target = db.scalar(select(Room).where(
        Room.id == body.target_room_id,
        Room.store_id == occupancy.store_id,
    ).with_for_update())
    if not target or target.room_type != "sofa" or not target.customer_selectable or target.operational_status != "active":
        raise HTTPException(status_code=400, detail="目标沙发不可选")
    if target.status != "available":
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_UNAVAILABLE",
            "message": "目标沙发暂不可用，请联系前台安排",
            "position_code": target.code,
            "state": target.status,
        })
    if target.id == occupancy.active_room_id:
        return occupancy_view(occupancy)
    if _active_occupancy_for_room(db, target.id):
        raise HTTPException(status_code=409, detail={"code": "POSITION_OCCUPIED", "message": "目标沙发已有顾客"})
    previous_room_id = occupancy.active_room_id
    occupancy.room_id = target.id
    occupancy.active_room_id = target.id
    occupancy.version += 1
    audit_occupancy(db, occupancy, "position_moved", "customer", session.id, {
        "from_room_id": previous_room_id,
        "to_room_id": target.id,
        "reason": body.reason,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "POSITION_OCCUPIED", "message": "目标沙发刚刚被占用"}) from exc
    db.refresh(occupancy)
    return occupancy_view(occupancy)


def _admin_live_map(db: Session, store_id: int) -> dict:
    expire_stale_holds(db, store_id)
    rooms = list(db.scalars(select(Room).where(Room.store_id == store_id).order_by(Room.sort_order, Room.id)))
    active = list(db.scalars(select(PositionOccupancy).where(
        PositionOccupancy.store_id == store_id,
        PositionOccupancy.active_room_id.is_not(None),
    )))
    occupancies = {item.active_room_id: item for item in active}
    sessions = {
        item.selection_session_id: db.get(SelectionSession, item.selection_session_id)
        for item in active
    }
    service_order_statuses = dict(db.execute(
        select(Visit.selection_session_id, ServiceOrder.status)
        .join(ServiceOrder, ServiceOrder.visit_id == Visit.id)
        .where(Visit.store_id == store_id, Visit.selection_session_id.is_not(None))
    ).all())
    positions = []
    for room in rooms:
        occupancy = occupancies.get(room.id)
        view = position_view(room, occupancy)
        session = sessions.get(occupancy.selection_session_id) if occupancy else None
        view["selection"] = None if not session else {
            "id": session.id,
            "status": session.status,
            "fulfillment_order_id": session.fulfillment_order_id,
            "service_order_status": service_order_statuses.get(session.id),
            "source": session.source,
            "device_label": session.device_label,
            "items": session.items,
            "pricing_snapshot": session.pricing_snapshot,
            "store_total_cents": session.store_total_cents,
            "member_total_cents": session.member_total_cents,
            "submitted_at": aware(session.submitted_at),
        }
        positions.append(view)
    return {"store_id": store_id, "positions": positions, "updated_at": utcnow()}


@router.get("/admin/live-service-position-map")
def admin_live_position_map(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_live_map(db, _staff_store_id(staff))


@router.post("/admin/kiosk-sessions")
def create_kiosk_session(
    body: KioskSessionIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    room = db.get(Room, body.room_id)
    if not room or room.store_id != store_id:
        raise HTTPException(status_code=404, detail="服务位不存在")
    session, occupancy, room, token, _, _ = _create_entry(db, EntrySessionIn(
        store_id=store_id,
        position_code=room.code,
        source="kiosk",
        device_label=body.device_label,
    ), None)
    audit_occupancy(db, occupancy, "kiosk_session_created", "staff", str(staff.id), {"room_id": room.id})
    db.commit()
    return {
        "session": _selection_view(session),
        "occupancy": occupancy_view(occupancy),
        "position": position_view(room, occupancy, current=True),
        "access_token": token,
    }


def _owned_occupancy(db: Session, occupancy_id: int, store_id: int) -> PositionOccupancy:
    occupancy = db.get(PositionOccupancy, occupancy_id)
    if not occupancy or occupancy.store_id != store_id or not occupancy.active_room_id:
        raise HTTPException(status_code=404, detail="活动占用不存在")
    return occupancy


@router.post("/admin/occupancies/{occupancy_id}/move")
def admin_move_occupancy(
    occupancy_id: int,
    body: MoveOccupancyIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    occupancy = _owned_occupancy(db, occupancy_id, store_id)
    session = db.get(SelectionSession, occupancy.selection_session_id)
    if session and session.fulfillment_order_id:
        raise HTTPException(status_code=409, detail={
            "code": "DIY_POSITION_LOCKED",
            "message": "该选单已由前台接待，请按当前服务位继续服务",
        })
    if body.version is not None and body.version != occupancy.version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT", "message": "服务位状态已变化，请刷新"})
    target = db.scalar(select(Room).where(
        Room.id == body.target_room_id,
        Room.store_id == store_id,
    ).with_for_update())
    if not target or target.operational_status != "active":
        raise HTTPException(status_code=400, detail="目标服务位不可用")
    if target.status != "available":
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_UNAVAILABLE",
            "message": "目标服务位暂不可用，请联系前台安排",
            "position_code": target.code,
            "state": target.status,
        })
    if target.id == occupancy.active_room_id:
        return occupancy_view(occupancy)
    if _active_occupancy_for_room(db, target.id):
        raise HTTPException(status_code=409, detail={"code": "POSITION_OCCUPIED", "message": "目标服务位已有顾客"})

    previous_room_id = occupancy.active_room_id
    occupancy.room_id = target.id
    occupancy.active_room_id = target.id
    occupancy.version += 1
    audit_occupancy(db, occupancy, "position_moved", "staff", str(staff.id), {
        "from_room_id": previous_room_id,
        "to_room_id": target.id,
        "reason": body.reason,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "POSITION_OCCUPIED", "message": "目标服务位刚刚被占用"}) from exc
    db.refresh(occupancy)
    return occupancy_view(occupancy)


def _admin_action(
    db: Session,
    occupancy: PositionOccupancy,
    action: str,
    body: OccupancyActionIn,
    staff,
) -> dict:
    before = occupancy.status
    now = utcnow()
    session = db.get(SelectionSession, occupancy.selection_session_id)
    fulfillment_service_order_status = None
    if session and session.fulfillment_order_id:
        fulfillment_service_order_status = db.scalar(
            select(ServiceOrder.status)
            .join(Visit, ServiceOrder.visit_id == Visit.id)
            .where(Visit.selection_session_id == session.id)
        )
    if (
        session
        and session.fulfillment_order_id
        and action != "force_release"
        and not (
            fulfillment_service_order_status == "completed"
            and action in {"confirm_departure", "finish_cleaning"}
        )
    ):
        raise HTTPException(status_code=409, detail={
            "code": "DIY_FULFILLMENT_OPERATION_REQUIRED",
            "message": "该选单已生成服务单，请在派钟服务流程完成现场操作",
        })
    if action == "start_service":
        if occupancy.status != "waiting_service":
            raise HTTPException(status_code=409, detail="只有待服务状态可以开始服务")
        occupancy.status = "in_service"
        occupancy.actual_start_at = now
        occupancy.expected_end_at = now + timedelta(minutes=body.expected_minutes or 60)
        for line in db.scalars(select(ServiceLine).where(
            ServiceLine.selection_session_id == occupancy.selection_session_id,
            ServiceLine.state == "pending",
        )):
            line.state = "in_service"
            line.started_at = now
    elif action == "finish_service":
        if occupancy.status != "in_service":
            raise HTTPException(status_code=409, detail="只有服务中状态可以结束服务")
        occupancy.status = "post_service_present"
        occupancy.actual_service_end_at = now
        for line in db.scalars(select(ServiceLine).where(
            ServiceLine.selection_session_id == occupancy.selection_session_id,
            ServiceLine.state.in_(("pending", "in_service")),
        )):
            line.state = "completed"
            line.completed_at = now
    elif action == "confirm_departure":
        if occupancy.status not in {"waiting_service", "in_service", "post_service_present"}:
            raise HTTPException(status_code=409, detail="当前状态不能确认离位")
        if occupancy.status == "in_service" and not occupancy.actual_service_end_at:
            occupancy.actual_service_end_at = now
        occupancy.status = "cleaning"
        occupancy.departed_at = now
    elif action == "finish_cleaning":
        if occupancy.status != "cleaning":
            raise HTTPException(status_code=409, detail="只有待清洁状态可以完成清洁")
        release_occupancy(occupancy, body.reason or "清洁完成", now=now)
        room = db.get(Room, occupancy.room_id)
        if room and room.store_id == occupancy.store_id:
            room.status = "available"
            room.used_count = 0
            room.current_tech = ""
    elif action == "force_release":
        if occupancy.status in {"in_service", "post_service_present", "cleaning"} and staff.role != "admin":
            raise HTTPException(status_code=403, detail="该状态需要店长权限释放")
        if not body.reason.strip():
            raise HTTPException(status_code=400, detail="强制释放必须填写原因")
        if occupancy.status in {"in_service", "post_service_present"}:
            occupancy.actual_service_end_at = occupancy.actual_service_end_at or now
            occupancy.departed_at = now
            occupancy.status = "cleaning"
            occupancy.hold_expires_at = None
            occupancy.release_reason = body.reason
            occupancy.version += 1
        elif occupancy.status == "waiting_service" and body.target_state == "cleaning":
            occupancy.departed_at = now
            occupancy.status = "cleaning"
            occupancy.hold_expires_at = None
            occupancy.release_reason = body.reason
            occupancy.version += 1
        else:
            release_occupancy(occupancy, body.reason, now=now)
        pending_changes = list(db.scalars(select(SelectionChangeRequest).where(
            SelectionChangeRequest.selection_session_id == occupancy.selection_session_id,
            SelectionChangeRequest.state == "awaiting_staff_confirmation",
        )))
        for change in pending_changes:
            change.state = "rejected"
            change.reason = f"服务位异常结束：{body.reason.strip()}"
            change.resolved_at = now
            change.resolved_by_staff_id = staff.id
            revision = db.get(SelectionRevision, change.selection_revision_id)
            if revision and revision.state == "awaiting_staff_confirmation":
                revision.state = "rejected"
    else:
        raise HTTPException(status_code=400, detail="不支持的服务位动作")
    if action not in {"finish_cleaning", "force_release"}:
        occupancy.version += 1
    audit_occupancy(db, occupancy, action, "staff", str(staff.id), {
        "from_status": before,
        "to_status": occupancy.status,
        "reason": body.reason,
        "reason_code": body.reason_code,
        "target_state": body.target_state,
    })
    db.commit()
    db.refresh(occupancy)
    return occupancy_view(occupancy)


@router.post("/admin/occupancies/{occupancy_id}/start-service")
def admin_start_service(occupancy_id: int, body: OccupancyActionIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_action(db, _owned_occupancy(db, occupancy_id, _staff_store_id(staff)), "start_service", body, staff)


@router.post("/admin/occupancies/{occupancy_id}/finish-service")
def admin_finish_service(occupancy_id: int, body: OccupancyActionIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_action(db, _owned_occupancy(db, occupancy_id, _staff_store_id(staff)), "finish_service", body, staff)


@router.post("/admin/occupancies/{occupancy_id}/confirm-departure")
def admin_confirm_departure(occupancy_id: int, body: OccupancyActionIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_action(db, _owned_occupancy(db, occupancy_id, _staff_store_id(staff)), "confirm_departure", body, staff)


@router.post("/admin/occupancies/{occupancy_id}/finish-cleaning")
def admin_finish_cleaning(occupancy_id: int, body: OccupancyActionIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_action(db, _owned_occupancy(db, occupancy_id, _staff_store_id(staff)), "finish_cleaning", body, staff)


@router.post("/admin/occupancies/{occupancy_id}/force-release")
def admin_force_release(occupancy_id: int, body: OccupancyActionIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    return _admin_action(db, _owned_occupancy(db, occupancy_id, _staff_store_id(staff)), "force_release", body, staff)
