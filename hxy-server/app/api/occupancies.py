"""扫码入口、服务位平面图和门店占用动作 API。"""

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, _staff_store_id, normalize_staff_role
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
from app.domain.occupancy_release_policy import (
    WAITING_SERVICE_TTL_MINUTES,
    list_release_candidates,
    release_selected_occupancies,
)
from app.models import AuditLog, BrowserInstance, PositionOccupancy, Room, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceLine, ServicePositionQr, Store, User
from app.models.service import ServiceOrder, Visit
from app.schemas.occupancy import (
    BulkReleaseIn,
    EntrySessionIn,
    KioskSessionIn,
    MoveOccupancyIn,
    OccupancyActionIn,
    RetainOccupancyIn,
)
from app.schemas.selection import SelectionSessionOut


router = APIRouter(tags=["service-position-occupancy"])


def _selection_view(session: SelectionSession) -> dict:
    return SelectionSessionOut.model_validate(session).model_dump()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_position_qr_token(store_id: int, position_code: str, source: str = "personal_qr") -> str:
    """生成兼容既有投放的 v1 签名；新管理端二维码统一使用持久化 v2。"""
    payload = {"v": 1, "store_id": int(store_id), "position_code": position_code, "source": source}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def _managed_position_qr_token_v2(qr: ServicePositionQr, position_code: str) -> str:
    """兼容已打印的 v2 码；新码改用更短的 v3 令牌。"""
    payload = {
        "v": 2,
        "qr_id": qr.public_id,
        "store_id": qr.store_id,
        "position_code": position_code,
        "source": qr.source,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def _managed_position_qr_token(qr: ServicePositionQr, position_code: str) -> str:
    """生成紧凑 v3 码。

    门店、服务位和来源均以持久化二维码记录为准，码面只保存不可猜测的
    public_id 与 128 位 HMAC 标签，减少现场打印二维码的模块密度。
    """
    del position_code
    public_id = qr.public_id.replace("-", "")
    payload = f"v3.{public_id}"
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).digest()[:16]
    ).decode().rstrip("=")
    return f"{payload}.{signature}"


def _qr_error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


def _verify_position_qr_token(
    db: Session,
    token: str,
    store_id: int,
    position_code: str,
    source: str,
) -> ServicePositionQr | None:
    if token.startswith("v3."):
        try:
            version, public_id, signature = token.split(".")
            if version != "v3" or len(public_id) != 32 or any(char not in "0123456789abcdef" for char in public_id):
                raise ValueError
            canonical_public_id = str(uuid.UUID(hex=public_id))
        except (ValueError, TypeError):
            raise _qr_error("QR_BINDING_INVALID", "二维码无效，请重新扫码")
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.jwt_secret.encode(), f"v3.{public_id}".encode(), hashlib.sha256).digest()[:16]
        ).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            raise _qr_error("QR_BINDING_INVALID", "二维码无效，请重新扫码")
        qr = db.scalar(select(ServicePositionQr).where(ServicePositionQr.public_id == canonical_public_id))
        if not qr:
            raise _qr_error("QR_BINDING_INVALID", "二维码不存在，请联系前台")
        if qr.status != "active":
            raise _qr_error("QR_DISABLED", "二维码已停用，请联系前台获取新二维码")
        room = db.get(Room, qr.room_id)
        if not room or qr.store_id != store_id or room.code != position_code or qr.source != source:
            raise _qr_error("QR_BINDING_INVALID", "二维码绑定信息已变化，请重新扫码")
        qr.last_accessed_at = utcnow()
        return qr

    try:
        raw, signature = token.split(".", 1)
        expected = hmac.new(settings.jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise _qr_error("QR_BINDING_INVALID", "二维码无效，请重新扫码")
    if not hmac.compare_digest(signature, expected):
        raise _qr_error("QR_BINDING_INVALID", "二维码无效，请重新扫码")
    if payload.get("store_id") != store_id or payload.get("position_code") != position_code or payload.get("source") != source:
        raise _qr_error("QR_BINDING_INVALID", "二维码与门店或服务位不匹配，请重新扫码")
    version = payload.get("v")
    if version == 1:
        if settings.environment == "production":
            raise _qr_error("QR_VERSION_EXPIRED", "该二维码已过期，请联系门店更换新二维码")
        # 本地迁移测试仍可读取 v1；生产入口只接受可撤销的 v2/v3 二维码。
        return None
    if version != 2 or not payload.get("qr_id"):
        raise _qr_error("QR_BINDING_INVALID", "二维码版本无效，请重新扫码")
    qr = db.scalar(select(ServicePositionQr).where(ServicePositionQr.public_id == payload["qr_id"]))
    if not qr:
        raise _qr_error("QR_BINDING_INVALID", "二维码不存在，请联系前台")
    if qr.status != "active":
        raise _qr_error("QR_DISABLED", "二维码已停用，请联系前台获取新二维码")
    room = db.get(Room, qr.room_id)
    if not room or qr.store_id != store_id or room.code != position_code or qr.source != source:
        raise _qr_error("QR_BINDING_INVALID", "二维码绑定信息已变化，请重新扫码")
    qr.last_accessed_at = utcnow()
    return qr


ANONYMOUS_COOKIE = "hxy_browser_token"


def _browser_customer(db: Session, request: Request | None) -> tuple[int, str, bool]:
    """读取或创建匿名顾客；凭证只通过 HttpOnly Cookie 传递。"""
    token = request.cookies.get(ANONYMOUS_COOKIE) if request else None
    if token:
        browser = db.scalar(select(BrowserInstance).where(BrowserInstance.token_hash == _hash_token(token)))
        if browser:
            customer = db.get(User, browser.customer_id)
            if not customer or not customer.openid.startswith("anon_"):
                # 兼容并自愈历史数据：旧登录流程曾把长期浏览器 Cookie 改绑到手机号账号，
                # 导致退出登录后创建的新选单仍按会员价计算。轮换回独立匿名身份，
                # 不影响已经归档到账号下的历史选单。
                anonymous = User(openid=f"anon_{uuid.uuid4().hex}")
                db.add(anonymous)
                db.flush()
                browser.customer_id = anonymous.id
                browser.last_seen_at = utcnow()
                return anonymous.id, token, False
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
    if body.entry_token:
        _verify_position_qr_token(db, body.entry_token, body.store_id, body.position_code, body.source)
    elif settings.environment == "production" and body.source in {"personal_qr", "room_qr"}:
        raise HTTPException(status_code=403, detail={"code": "QR_BINDING_REQUIRED", "message": "请使用门店服务位二维码进入"})
    expire_stale_holds(db, body.store_id)
    store = db.get(Store, body.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    room = db.scalar(select(Room).where(
        Room.store_id == body.store_id,
        Room.code == body.position_code,
    ).with_for_update())
    if not room or room.operational_status != "active" or not room.is_service_position or room.is_space_container:
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
    rolled_over_after_service = False
    if existing:
        existing_session = db.get(SelectionSession, existing.active_session_id)
        if (
            body.start_new_after_service
            and existing_session
            and existing_session.customer_id == anonymous_customer_id
            and existing_session.status in {"submitted", "confirmed"}
            and existing.status == "post_service_present"
        ):
            # 只结束 DIY 对旧会话的活动引用；不改变物理房位状态，也不删除旧单或评价。
            existing.active_room_id = None
            existing.active_session_id = None
            existing.version += 1
            audit_occupancy(db, existing, "next_selection_started", "customer", existing_session.id, {
                "room_id": room.id,
                "position_code": room.code,
            })
            db.flush()
            existing = None
            rolled_over_after_service = True
        elif body.start_new_after_service and existing_session and existing_session.customer_id != anonymous_customer_id:
            raise HTTPException(status_code=409, detail={
                "code": "POSITION_OCCUPIED",
                "message": "该服务位已有顾客，请核对二维码或联系前台",
                "position_code": room.code,
                "state": existing.status,
            })
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
    if room.status != "available" and not rolled_over_after_service:
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
        source="bound_qr" if body.entry_token else body.source,
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
    if body.source == "bound_qr":
        raise HTTPException(status_code=403, detail={
            "code": "ENTRY_SOURCE_FORBIDDEN",
            "message": "该入口来源仅由服务端在验证二维码后记录",
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


@router.get("/admin/service-positions/{room_id}/qr-link")
def admin_position_qr_link(room_id: int, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    staff = _current_staff(authorization, db)
    room = db.get(Room, room_id)
    store_id = _staff_store_id(staff)
    if not room or room.store_id != store_id:
        raise HTTPException(status_code=404, detail="服务位不存在")
    if not room.is_service_position or room.is_space_container:
        raise HTTPException(status_code=400, detail="房间是空间容器，请为具体沙发或床位生成二维码")
    qr = db.scalar(select(ServicePositionQr).where(
        ServicePositionQr.store_id == store_id,
        ServicePositionQr.room_id == room.id,
        ServicePositionQr.replaced_by_id.is_(None),
    ).order_by(ServicePositionQr.id.desc()))
    if not qr:
        if room.operational_status != "active":
            raise HTTPException(status_code=409, detail={
                "code": "SERVICE_POSITION_DISABLED",
                "message": "服务位已停用，请重新启用后再生成二维码",
            })
        if normalize_staff_role(staff.role, staff.technician_id) != "manager":
            raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可创建服务位二维码"})
        qr = _create_managed_qr(db, room, staff.id)
        _audit_qr(db, staff, qr, "service_position_qr_created", {"room_id": room.id})
        db.commit()
        db.refresh(qr)
    return _managed_qr_view(qr, room)


@router.patch("/admin/service-positions/{room_id}/operational-status")
def update_service_position_operational_status(
    room_id: int,
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """切换 DIY 服务位入口，不触发智慧宝物理资源操作。"""
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可停用或启用服务位"})
    room = db.scalar(select(Room).where(
        Room.id == room_id,
        Room.store_id == _staff_store_id(staff),
    ).with_for_update())
    if not room:
        raise HTTPException(status_code=404, detail="服务位不存在")
    if room.is_space_container or not room.is_service_position:
        raise HTTPException(status_code=400, detail="房间是空间容器，请操作具体服务位")
    target_status = body.get("operational_status")
    if target_status not in {"active", "inactive"}:
        raise HTTPException(status_code=422, detail="服务位状态只能是 active 或 inactive")
    active_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == room.id,
    ))
    if active_occupancy:
        raise HTTPException(status_code=409, detail={
            "code": "POSITION_OCCUPIED",
            "message": "当前服务位有活动占用，请完成服务流程后再调整配置",
        })
    previous_status = room.operational_status
    if previous_status != target_status:
        room.operational_status = target_status
        action = "service_position_disabled" if target_status == "inactive" else "service_position_enabled"
        db.add(AuditLog(
            actor_type="staff",
            actor_id=str(staff.id),
            store_id=room.store_id,
            action=action,
            entity_type="service_position",
            entity_id=str(room.id),
            detail={
                "room_id": room.id,
                "from_operational_status": previous_status,
                "to_operational_status": target_status,
                "reason": str(body.get("reason") or "")[:256],
            },
        ))
        db.commit()
        db.refresh(room)
    return position_view(room)


def _create_managed_qr(db: Session, room: Room, staff_id: int) -> ServicePositionQr:
    source = "room_qr" if room.room_type in {"room", "bed"} else "personal_qr"
    qr = ServicePositionQr(
        public_id=str(uuid.uuid4()),
        store_id=room.store_id,
        room_id=room.id,
        source=source,
        status="active",
        created_by_staff_id=staff_id,
    )
    db.add(qr)
    db.flush()
    return qr


def _managed_qr_view(qr: ServicePositionQr, room: Room) -> dict:
    token = _managed_position_qr_token(qr, room.code)
    base = settings.h5_public_base_url.rstrip("/") + "/"
    from urllib.parse import urlencode
    url = base + "?" + urlencode({"store": qr.store_id, "seat": room.code, "source": qr.source, "qr": token})
    return {
        "qr_id": qr.id,
        "store_id": qr.store_id,
        "room_id": qr.room_id,
        "position_code": room.code,
        "position_name": room.name,
        "source": qr.source,
        "status": qr.status,
        "token": token,
        "url": url,
        "last_accessed_at": qr.last_accessed_at.isoformat() if qr.last_accessed_at else None,
        "created_at": qr.created_at.isoformat() if qr.created_at else None,
    }


def _audit_qr(db: Session, staff, qr: ServicePositionQr, action: str, detail: dict) -> None:
    db.add(AuditLog(
        actor_type="staff",
        actor_id=str(staff.id),
        store_id=qr.store_id,
        action=action,
        entity_type="service_position_qr",
        entity_id=str(qr.id),
        detail={"store_id": qr.store_id, "room_id": qr.room_id, **detail},
    ))


def _owned_qr(db: Session, qr_id: int, staff) -> ServicePositionQr:
    qr = db.get(ServicePositionQr, qr_id)
    if not qr or qr.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="服务位二维码不存在")
    return qr


@router.patch("/admin/service-position-qrs/{qr_id}")
def update_service_position_qr(
    qr_id: int,
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可修改服务位二维码"})
    qr = _owned_qr(db, qr_id, staff)
    target_status = body.get("status")
    if target_status not in {"active", "disabled"}:
        raise HTTPException(status_code=422, detail="二维码状态只能是 active 或 disabled")
    if qr.replaced_by_id and target_status == "active":
        raise HTTPException(status_code=409, detail="该二维码已被替换，不能重新启用")
    if target_status == "active":
        active = db.scalar(select(ServicePositionQr).where(
            ServicePositionQr.room_id == qr.room_id,
            ServicePositionQr.status == "active",
            ServicePositionQr.id != qr.id,
        ))
        if active:
            raise HTTPException(status_code=409, detail="该服务位已有启用中的二维码")
        room = db.get(Room, qr.room_id)
        if not room or room.operational_status != "active" or room.is_space_container or not room.is_service_position:
            raise HTTPException(status_code=409, detail="服务位当前不可启用二维码")
        qr.disabled_at = None
    else:
        qr.disabled_at = utcnow()
    qr.status = target_status
    _audit_qr(db, staff, qr, f"service_position_qr_{target_status}", {"reason": str(body.get("reason") or "")[:256]})
    db.commit()
    db.refresh(qr)
    return _managed_qr_view(qr, db.get(Room, qr.room_id))


@router.post("/admin/service-position-qrs/{qr_id}/regenerate")
def regenerate_service_position_qr(
    qr_id: int,
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可重新生成服务位二维码"})
    old = _owned_qr(db, qr_id, staff)
    if old.replaced_by_id:
        raise HTTPException(status_code=409, detail={
            "code": "QR_REPLACED",
            "message": "该二维码已被替换，不能再次重新生成",
        })
    room = db.get(Room, old.room_id)
    if not room or room.is_space_container or not room.is_service_position:
        raise HTTPException(status_code=409, detail="服务位当前不能生成二维码")
    if room.operational_status != "active":
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_POSITION_DISABLED",
            "message": "服务位已停用，请重新启用后再生成二维码",
        })
    old.status = "disabled"
    old.disabled_at = utcnow()
    db.flush()
    new = _create_managed_qr(db, room, staff.id)
    old.replaced_by_id = new.id
    reason = str(body.get("reason") or "重新生成现场二维码")[:256]
    _audit_qr(db, staff, old, "service_position_qr_replaced", {"reason": reason, "new_qr_id": new.id})
    _audit_qr(db, staff, new, "service_position_qr_created", {"reason": reason, "old_qr_id": old.id})
    db.commit()
    db.refresh(new)
    return _managed_qr_view(new, room)


@router.post("/admin/service-position-qrs/{qr_id}/rebind")
def rebind_service_position_qr(
    qr_id: int,
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可调整二维码绑定"})
    old = _owned_qr(db, qr_id, staff)
    target_room_id = body.get("target_room_id")
    target = db.get(Room, target_room_id) if target_room_id else None
    if not target or target.store_id != old.store_id:
        raise HTTPException(status_code=404, detail="目标服务位不存在")
    if target.is_space_container or not target.is_service_position or target.operational_status != "active":
        raise HTTPException(status_code=409, detail="目标位置不是可用的实际服务位")
    active = db.scalar(select(ServicePositionQr).where(
        ServicePositionQr.room_id == target.id,
        ServicePositionQr.status == "active",
    ))
    if active:
        raise HTTPException(status_code=409, detail="目标服务位已有启用中的二维码，请先停用")
    new = _create_managed_qr(db, target, staff.id)
    old.status = "disabled"
    old.disabled_at = utcnow()
    old.replaced_by_id = new.id
    reason = str(body.get("reason") or "调整二维码绑定服务位")[:256]
    _audit_qr(db, staff, old, "service_position_qr_rebound", {
        "reason": reason,
        "from_room_id": old.room_id,
        "to_room_id": target.id,
        "new_qr_id": new.id,
    })
    _audit_qr(db, staff, new, "service_position_qr_created", {"reason": reason, "old_qr_id": old.id})
    db.commit()
    db.refresh(new)
    return _managed_qr_view(new, target)


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
        Room.is_service_position.is_(True),
        Room.is_space_container.is_(False),
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
    if occupancy.source in {"kiosk", "bound_qr", "room_qr"} or (current_room and current_room.room_type == "room"):
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
    rooms = list(db.scalars(select(Room).where(
        Room.store_id == store_id,
        Room.is_service_position.is_(True),
        Room.is_space_container.is_(False),
    ).order_by(Room.sort_order, Room.id)))
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


@router.post("/admin/occupancies/{occupancy_id}/retain")
def retain_position_occupancy(
    occupancy_id: int,
    body: RetainOccupancyIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    occupancy = db.scalar(
        select(PositionOccupancy)
        .where(
            PositionOccupancy.id == occupancy_id,
            PositionOccupancy.store_id == store_id,
            PositionOccupancy.active_room_id.is_not(None),
        )
        .with_for_update()
    )
    if occupancy is None:
        raise HTTPException(status_code=404, detail="活动占用不存在")
    if occupancy.version != body.version:
        raise HTTPException(status_code=409, detail={
            "code": "VERSION_CONFLICT",
            "message": "服务位状态已变化，请刷新",
        })
    session = db.scalar(
        select(SelectionSession)
        .where(SelectionSession.id == occupancy.selection_session_id)
        .with_for_update()
    )
    if (
        occupancy.status != "waiting_service"
        or occupancy.actual_start_at is not None
        or session is None
        or session.status != "submitted"
        or session.fulfillment_order_id is not None
        or session.submitted_at is None
    ):
        raise HTTPException(status_code=409, detail={
            "code": "OCCUPANCY_NOT_RETAINABLE",
            "message": "当前服务位已不能续留，请刷新状态",
        })
    now = utcnow()
    default_deadline = aware(session.submitted_at) + timedelta(
        minutes=WAITING_SERVICE_TTL_MINUTES
    )
    current_retention = aware(occupancy.retained_until)
    bases = [now, default_deadline]
    if current_retention is not None:
        bases.append(current_retention)
    occupancy.retained_until = max(bases) + timedelta(minutes=body.minutes)
    occupancy.version += 1
    audit_occupancy(db, occupancy, "occupancy_retained", "staff", str(staff.id), {
        "minutes": body.minutes,
        "reason": body.reason,
        "retained_until": occupancy.retained_until.isoformat(),
    })
    db.commit()
    db.refresh(occupancy)
    return occupancy_view(occupancy)


@router.get("/admin/occupancies/release-candidates")
def admin_release_candidates(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    candidates = list_release_candidates(
        db,
        utcnow(),
        store_id=_staff_store_id(staff),
    )
    return {"items": [
        {
            "occupancy_id": candidate.occupancy_id,
            "version": candidate.version,
            "room_id": candidate.room_id,
            "room_code": candidate.room_code,
            "status": candidate.status,
            "selection_session_id": candidate.selection_session_id,
            "due_at": candidate.due_at,
            "overdue_seconds": candidate.overdue_seconds,
            "reason_code": candidate.reason_code,
        }
        for candidate in candidates
    ]}


@router.post("/admin/occupancies/bulk-release")
def admin_bulk_release_occupancies(
    body: BulkReleaseIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    staff = _current_staff(authorization, db)
    if staff.role != "admin":
        raise HTTPException(status_code=403, detail="只有店长可以批量释放服务位")
    expected_versions = {item.occupancy_id: item.version for item in body.items}
    if len(expected_versions) != len(body.items):
        raise HTTPException(status_code=422, detail="不能重复提交同一个服务位")
    result = release_selected_occupancies(
        db,
        utcnow(),
        expected_versions,
        store_id=_staff_store_id(staff),
        trigger=str(staff.id),
        release_reason=body.reason,
    )
    return {
        "released": list(result.released_ids),
        "skipped": [
            {"occupancy_id": occupancy_id, "reason": reason}
            for occupancy_id, reason in result.skipped
        ],
    }


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
