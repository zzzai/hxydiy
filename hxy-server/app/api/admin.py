"""管理后台 API（HXYOS 第一块）：员工登录、今日预约、订单核销、行为看板。

- 员工账号由 seed 创建（初始密码随机生成，见服务器 admin-credentials.txt）
- 状态机：paid/confirmed -> checked_in(核销) -> completed
"""

import csv
import hashlib
import io
import os
import time
from collections import Counter, defaultdict
from datetime import date as date_type, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditLog,
    CouponTemplate,
    EventLog,
    Order,
    OrderEvent,
    PositionOccupancy,
    Room,
    ServiceFeedback,
    SelectionSession,
    Staff,
    Store,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])

PBKDF2_ITERATIONS = 120_000
LOGIN_FAIL_LIMIT = 5          # 5 次失败
LOGIN_LOCK_SECONDS = 600      # 锁定 10 分钟

# 单实例内存限流（多实例部署时需换共享存储）
_login_fails: dict[str, list[float]] = defaultdict(list)


def _check_login_lock(username: str) -> None:
    now = time.time()
    _login_fails[username] = [t for t in _login_fails[username]
                              if now - t < LOGIN_LOCK_SECONDS]
    if len(_login_fails[username]) >= LOGIN_FAIL_LIMIT:
        raise HTTPException(status_code=429, detail="尝试次数过多，请 10 分钟后再试")


def _record_login_fail(username: str) -> None:
    _login_fails[username].append(time.time())


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    return hash_password(password, salt) == stored


def create_staff_token(staff_id: int, role: str, credentials_version: int = 1) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=12)
    payload = {
        "sub": str(staff_id),
        "role": role,
        "token_type": "staff",
        "credentials_version": int(credentials_version),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def normalize_staff_role(role: str | None, technician_id: int | None = None) -> str:
    """Return the public role contract while accepting legacy database values."""
    if role in {"admin", "manager"}:
        return "manager"
    if role == "technician" and technician_id:
        return "technician"
    raise ValueError("staff role is not normalized or technician binding is missing")


def staff_snapshot(staff: Staff, store_name: str = "") -> dict:
    # 未绑定门店的 admin 是总部管理员；绑定门店的历史 admin 继续按店长对外呈现。
    public_role = "admin" if staff.role == "admin" and staff.store_id is None else normalize_staff_role(staff.role, staff.technician_id)
    return {
        "id": staff.id,
        "name": staff.name,
        "role": public_role,
        "store_id": staff.store_id,
        "technician_id": staff.technician_id,
        "store_name": store_name,
    }


def _current_staff(authorization: str | None, db: Session) -> Staff:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_REQUIRED", "message": "请先登录"})
    try:
        payload = jwt.decode(authorization[7:], settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_EXPIRED", "message": "登录已过期"})
    if payload.get("token_type") != "staff":
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN_TYPE", "message": "令牌类型无效"})
    staff = db.get(Staff, int(payload["sub"]))
    if not staff or staff.status != "active":
        raise HTTPException(status_code=401, detail={"code": "STAFF_ACCOUNT_UNAVAILABLE", "message": "账号不可用"})
    token_version = payload.get("credentials_version", 1)
    if int(token_version) != int(staff.credentials_version or 1):
        raise HTTPException(status_code=401, detail={"code": "STAFF_SESSION_REVOKED", "message": "登录状态已失效，请重新登录"})
    if staff.temporary_expires_at is not None:
        expires_at = staff.temporary_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise HTTPException(status_code=401, detail={"code": "STAFF_ACCOUNT_EXPIRED", "message": "临时账号已过期，请联系管理员"})
    if staff.role == "staff" and not staff.technician_id:
        raise HTTPException(status_code=403, detail={"code": "ROLE_MIGRATION_REQUIRED", "message": "员工账号尚未完成角色迁移"})
    if staff.role not in {"admin", "manager", "technician"}:
        raise HTTPException(status_code=403, detail={"code": "INVALID_STAFF_ROLE", "message": "员工角色无效"})
    if staff.role == "technician" and not staff.technician_id:
        raise HTTPException(status_code=403, detail={"code": "TECHNICIAN_BINDING_REQUIRED", "message": "技师账号未绑定技师档案"})
    return staff


def current_store_context(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Staff:
    """认证员工并确保其绑定门店，供后台 endpoint 复用。"""
    staff = _current_staff(authorization, db)
    _staff_store_id(staff)
    return staff


def require_manager(staff: Staff = Depends(current_store_context)) -> Staff:
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可执行此操作"})
    return staff


def require_technician(staff: Staff = Depends(current_store_context)) -> Staff:
    if normalize_staff_role(staff.role, staff.technician_id) != "technician" or not staff.technician_id:
        raise HTTPException(status_code=403, detail={"code": "TECHNICIAN_REQUIRED", "message": "仅已绑定技师可执行此操作"})
    return staff


def _staff_store_id(staff: Staff) -> int:
    if not staff.store_id:
        raise HTTPException(status_code=403, detail="当前账号未绑定门店")
    return staff.store_id


def _owned_order(db: Session, order_id: int, staff: Staff) -> Order:
    order = db.get(Order, order_id)
    if not order or order.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def _record_event(db: Session, order_id: int, from_status: str, to_status: str,
                  action: str, operator: str, reason: str = "") -> None:
    db.add(OrderEvent(
        order_id=order_id, from_status=from_status, to_status=to_status,
        action=action, operator=operator, reason=reason,
    ))


@router.post("/login")
def staff_login(body: dict, db: Session = Depends(get_db)) -> dict:
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    _check_login_lock(username)
    staff = db.scalar(select(Staff).where(Staff.username == username))
    if not staff or staff.status != "active" or not verify_password(password, staff.password_hash):
        _record_login_fail(username)
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if staff.temporary_expires_at is not None:
        expires_at = staff.temporary_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            _record_login_fail(username)
            raise HTTPException(status_code=401, detail="临时账号已过期，请联系管理员")
    if staff.role == "staff" and not staff.technician_id:
        raise HTTPException(status_code=403, detail={"code": "ROLE_MIGRATION_REQUIRED", "message": "员工账号尚未完成角色迁移"})
    if staff.role not in {"admin", "manager", "technician"}:
        raise HTTPException(status_code=403, detail={"code": "INVALID_STAFF_ROLE", "message": "员工角色无效"})
    if staff.role == "technician" and not staff.technician_id:
        raise HTTPException(status_code=403, detail={"code": "TECHNICIAN_BINDING_REQUIRED", "message": "技师账号未绑定技师档案"})
    store = db.get(Store, staff.store_id) if staff.store_id else None
    return {
        "token": create_staff_token(staff.id, staff.role, staff.credentials_version),
        "staff": {
            "id": staff.id,
            "name": staff.name,
            **staff_snapshot(staff, store.name if store else ""),
        },
    }


@router.get("/today-appointments")
def today_appointments(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """今日预约（已支付/已确认/已核销，按预约时间排序）。"""
    staff = _current_staff(authorization, db)
    store_id = _staff_store_id(staff)
    today = datetime.now().date().isoformat()
    orders = list(db.scalars(select(Order).where(
        Order.booking_date == today,
        Order.store_id == store_id,
        Order.status.in_(["paid", "confirmed", "checked_in", "in_service"]),
    ).order_by(Order.booking_time)))
    return {"date": today, "items": [_order_summary(o) for o in orders], "total": len(orders)}


@router.get("/stats")
def admin_stats(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """经营统计：今日订单/营业额/待核销/访问量/新增用户。"""
    staff = _current_staff(authorization, db)
    _require_manager_staff(staff)
    store_id = _staff_store_id(staff)
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=now.hour, minutes=now.minute,
                                seconds=now.second, microseconds=now.microsecond)

    orders_today = list(db.scalars(select(Order).where(
        Order.created_at >= day_start,
        Order.store_id == store_id,
    )))
    paid_today = [o for o in orders_today if o.pay_status == "paid"]
    valid_today = [o for o in orders_today if o.status not in ("cancelled", "expired")]

    pending_checkin = len(list(db.scalars(select(Order).where(
        Order.status.in_(["paid", "confirmed"]),
        Order.store_id == store_id,
    ))))

    from app.models import EventLog, User
    page_views = len(list(db.scalars(select(EventLog).where(
        EventLog.event == "page_view",
        EventLog.store_id == store_id,
        EventLog.created_at >= day_start,
    ))))
    store_order_users = select(Order.user_id).where(
        Order.store_id == store_id,
        Order.user_id.is_not(None),
    )
    store_selection_users = select(SelectionSession.customer_id).where(
        SelectionSession.store_id == store_id,
        SelectionSession.customer_id.is_not(None),
    )
    new_users = len(list(db.scalars(select(User).where(
        User.created_at >= day_start,
        or_(
            User.id.in_(store_order_users),
            User.id.in_(store_selection_users),
        ),
    ))))

    return {
        "date": now.date().isoformat(),
        "orders_count": len(valid_today),
        "paid_amount_cents": sum(o.pay_amount_cents for o in paid_today),
        "paid_count": len(paid_today),
        "pending_checkin": pending_checkin,
        "page_views": page_views,
        "new_users": new_users,
    }


def _summary_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _summary_event_identity(event: EventLog) -> str:
    data = event.data or {}
    for key in ("anonymous_id", "client_session_id", "browser_id"):
        value = data.get(key)
        if value:
            return f"{key}:{value}"
    if event.user_id:
        return f"user:{event.user_id}"
    return f"event:{event.id}"


def _summary_period(
    start_date: date_type | None,
    end_date: date_type | None,
) -> tuple[date_type, date_type, datetime, datetime]:
    end = end_date or datetime.now(timezone.utc).date()
    start = start_date or (end - timedelta(days=6))
    if start > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return start, end, start_at, end_at


@router.get("/operations-summary")
def operations_summary(
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    store_id: int | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """经营汇总：交易、顾客、去重漏斗、服务位和评价。"""
    staff = _require_admin(authorization, db)
    if staff.store_id is None:
        raise HTTPException(status_code=403, detail={"code": "STORE_SCOPE_REQUIRED", "message": "必须绑定本店门店"})
    if staff.store_id is not None and store_id not in (None, staff.store_id):
        raise HTTPException(status_code=403, detail="不能查询其他门店数据")
    selected_store_id = staff.store_id if staff.store_id is not None else store_id
    start, end, start_at, end_at = _summary_period(start_date, end_date)

    order_stmt = select(Order).where(
        Order.created_at >= start_at,
        Order.created_at < end_at,
        Order.pay_status == "paid",
        Order.status.not_in(("cancelled", "expired", "refunded", "refund_rejected")),
    )
    if selected_store_id is not None:
        order_stmt = order_stmt.where(Order.store_id == selected_store_id)
    orders = list(db.scalars(order_stmt))
    user_ids = {order.user_id for order in orders if order.user_id}
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids)))
    } if user_ids else {}

    previous_order_stmt = select(Order.user_id).where(
        Order.created_at < start_at,
        Order.pay_status == "paid",
        Order.status.not_in(("cancelled", "expired", "refunded", "refund_rejected")),
        Order.user_id.in_(user_ids),
    ) if user_ids else None
    previous_user_ids = set(db.scalars(previous_order_stmt)) if previous_order_stmt is not None else set()
    customer_users = [users[user_id] for user_id in user_ids if user_id in users]
    customer_user_ids = {
        user.id for user in customer_users
        if not user.openid.startswith("anon_") and not user.openid.startswith("counter_selection_")
    }

    event_stmt = select(EventLog).where(
        EventLog.created_at >= start_at,
        EventLog.created_at < end_at,
    )
    events = list(db.scalars(event_stmt))
    scoped_events = []
    for event in events:
        # 门店归属只信任规范化列，绝不采信客户端可写的 data.store_id。
        if selected_store_id is not None and event.store_id != selected_store_id:
            continue
        if selected_store_id is None and event.store_id is None:
            continue
        scoped_events.append(event)

    funnel = {}
    funnel_events = ("diy_entry_view", "project_view", "project_config_save",
                     "selection_submit_success", "feedback_submit_success")
    for event_name in funnel_events:
        funnel[event_name] = len({
            _summary_event_identity(event)
            for event in scoped_events
            if event.event == event_name
        })
    identity_events = {
        _summary_event_identity(event)
        for event in scoped_events
        if event.event in {"anonymous_to_logged_in", "phone_login_merge", "identity_bind"}
    }

    room_stmt = select(Room).where(Room.is_service_position.is_(True), Room.is_space_container.is_(False))
    if selected_store_id is not None:
        room_stmt = room_stmt.where(Room.store_id == selected_store_id)
    rooms = list(db.scalars(room_stmt))
    room_statuses = Counter(room.status for room in rooms)
    occupancy_stmt = select(PositionOccupancy).where(
        PositionOccupancy.created_at < end_at,
        (PositionOccupancy.released_at.is_(None) | (PositionOccupancy.released_at >= start_at)),
    )
    if selected_store_id is not None:
        occupancy_stmt = occupancy_stmt.where(PositionOccupancy.store_id == selected_store_id)
    occupancies = list(db.scalars(occupancy_stmt))
    occupancy_statuses = Counter(occupancy.status for occupancy in occupancies)
    completed_occupancies = [
        occupancy for occupancy in occupancies
        if _summary_utc(occupancy.actual_start_at)
        and _summary_utc(occupancy.actual_service_end_at)
    ]
    service_minutes = [
        (_summary_utc(occupancy.actual_service_end_at) - _summary_utc(occupancy.actual_start_at)).total_seconds() / 60
        for occupancy in completed_occupancies
    ]
    departure_to_release_minutes = [
        (_summary_utc(occupancy.released_at) - _summary_utc(occupancy.departed_at)).total_seconds() / 60
        for occupancy in occupancies
        if _summary_utc(occupancy.departed_at) and _summary_utc(occupancy.released_at)
    ]
    turnover_count = sum(
        1 for occupancy in occupancies
        if start_at <= _summary_utc(occupancy.released_at) < end_at
    )
    occupancy_ids = {str(occupancy.id) for occupancy in occupancies}
    exception_audit_stmt = select(AuditLog).where(
        AuditLog.action == "force_release",
        AuditLog.entity_type == "position_occupancy",
        AuditLog.entity_id.in_(occupancy_ids),
        AuditLog.created_at >= start_at,
        AuditLog.created_at < end_at,
    ) if occupancy_ids else None
    exception_release_count = len(list(db.scalars(exception_audit_stmt))) if exception_audit_stmt is not None else 0
    utilization_minutes = 0.0
    for occupancy in completed_occupancies:
        service_start = max(_summary_utc(occupancy.actual_start_at), start_at)
        service_end = min(_summary_utc(occupancy.actual_service_end_at), end_at)
        if service_end > service_start:
            utilization_minutes += (service_end - service_start).total_seconds() / 60
    capacity_minutes = len(rooms) * (end_at - start_at).total_seconds() / 60
    utilization_percent = round(utilization_minutes / capacity_minutes * 100, 2) if capacity_minutes else 0

    funnel_rates = {}
    for previous_name, current_name in zip(funnel_events, funnel_events[1:]):
        previous_count = funnel[previous_name]
        funnel_rates[f"{previous_name}_to_{current_name}_percent"] = round(
            funnel[current_name] / previous_count * 100, 2
        ) if previous_count else 0
    funnel_rates["project_view_to_selection_submit_success_percent"] = round(
        funnel["selection_submit_success"] / funnel["project_view"] * 100, 2
    ) if funnel["project_view"] else 0

    from sqlalchemy import func
    feedback_stmt = select(ServiceFeedback).where(
        ServiceFeedback.created_at >= start_at,
        ServiceFeedback.created_at < end_at,
    )
    if selected_store_id is not None:
        feedback_stmt = feedback_stmt.where(ServiceFeedback.store_id == selected_store_id)
    feedback = list(db.scalars(feedback_stmt))
    ratings = [item.rating for item in feedback]

    return {
        "period": {"start_date": start.isoformat(), "end_date": end.isoformat(), "store_id": selected_store_id},
        "transactions": {
            "orders_count": len(orders),
            "paid_count": len(orders),
            "gross_amount_cents": sum(order.total_amount_cents for order in orders),
            "paid_amount_cents": sum(order.pay_amount_cents for order in orders),
            "discount_cents": sum(order.discount_cents for order in orders),
            "member_discount_cents": sum(order.member_discount_cents for order in orders),
        },
        "customers": {
            "new_count": sum(1 for user in customer_users if user.id in customer_user_ids and start_at <= _summary_utc(user.created_at) < end_at),
            "repeat_count": len(customer_user_ids & previous_user_ids),
            "member_count": sum(1 for user in customer_users if user.id in customer_user_ids and user.is_member),
            "anonymous_to_logged_in_count": len(identity_events),
        },
        "funnel": funnel,
        "funnel_rates": funnel_rates,
        "service_positions": {
            "total_count": len(rooms),
            "status_counts": dict(room_statuses),
            "occupancy_status_counts": dict(occupancy_statuses),
            "active_count": sum(count for status, count in occupancy_statuses.items() if status in {"held", "waiting_service", "in_service", "post_service_present", "cleaning"}),
            "operations": {
                "completed_services_count": len(completed_occupancies),
                "average_service_minutes": round(sum(service_minutes) / len(service_minutes), 2) if service_minutes else 0,
                "average_departure_to_release_minutes": round(sum(departure_to_release_minutes) / len(departure_to_release_minutes), 2) if departure_to_release_minutes else 0,
                "turnover_count": turnover_count,
                "utilization_percent": utilization_percent,
                "exception_release_count": exception_release_count,
                "cleaning_minutes_available": False,
            },
        },
        "feedback": {
            "count": len(feedback),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "low_rating_count": sum(1 for rating in ratings if rating <= 2),
        },
    }


def _redact_audit_value(value, key: str = ""):
    lowered = key.lower()
    if isinstance(value, dict):
        return {name: _redact_audit_value(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_audit_value(item, key) for item in value]
    if value is None:
        return None
    if any(marker in lowered for marker in ("token", "password", "secret", "credential", "access_key")):
        return "[REDACTED]"
    if "phone" in lowered or "mobile" in lowered:
        text = str(value)
        return f"{text[:3]}****{text[-4:]}" if len(text) >= 7 else "****"
    if any(marker in lowered for marker in ("openid", "subject_id", "external_id")):
        text = str(value)
        return f"{text[:4]}****{text[-4:]}" if len(text) >= 8 else "****"
    return value


def _audit_rows(
    db: Session,
    staff: Staff,
    start_date: date_type | None,
    end_date: date_type | None,
    store_id: int | None,
    action: str | None,
    employee_id: str | None,
) -> list[AuditLog]:
    if staff.store_id is not None and store_id not in (None, staff.store_id):
        raise HTTPException(status_code=403, detail="不能查询其他门店数据")
    selected_store_id = staff.store_id if staff.store_id is not None else store_id
    _, _, start_at, end_at = _summary_period(start_date, end_date)
    stmt = select(AuditLog).where(
        AuditLog.created_at >= start_at,
        AuditLog.created_at < end_at,
    ).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if employee_id:
        stmt = stmt.where(AuditLog.actor_id == employee_id)
    if selected_store_id is not None:
        # 新记录走明确列；历史记录在迁移回填前仅允许按旧 detail.store_id
        # 兼容读取，且仍在 SQL 层完成门店过滤。
        legacy_store_id = AuditLog.detail["store_id"].as_integer()
        stmt = stmt.where(or_(
            AuditLog.store_id == selected_store_id,
            (AuditLog.store_id.is_(None) & (legacy_store_id == selected_store_id)),
        ))
    return list(db.scalars(stmt))


def _audit_row_out(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "store_id": row.store_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "detail": _redact_audit_value(row.detail or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/audit-logs")
def audit_logs(
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    store_id: int | None = None,
    action: str | None = None,
    employee_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    export: bool = False,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """审计查询和脱敏 CSV 导出，仅管理员可访问。"""
    staff = _require_admin(authorization, db)
    rows = _audit_rows(db, staff, start_date, end_date, store_id, action, employee_id)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    output_rows = [_audit_row_out(row) for row in rows]
    if export:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["id", "created_at", "actor_type", "actor_id", "store_id", "action", "entity_type", "entity_id", "detail"])
        for item in output_rows:
            writer.writerow([
                item["id"], item["created_at"], item["actor_type"], item["actor_id"], item["store_id"],
                item["action"], item["entity_type"], item["entity_id"], item["detail"],
            ])
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=\"audit-logs.csv\""},
        )
    offset = (page - 1) * page_size
    return {
        "items": output_rows[offset:offset + page_size],
        "total": len(output_rows),
        "page": page,
        "page_size": page_size,
    }


@router.post("/orders/{order_id}/check-in")
def check_in_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """到店核销：paid/confirmed -> checked_in。"""
    staff = _current_staff(authorization, db)
    _require_manager_staff(staff)
    order = _owned_order(db, order_id, staff)
    if order.status not in ("paid", "confirmed"):
        raise HTTPException(status_code=400, detail=f"当前状态({order.status})不可核销")
    _record_event(db, order.id, order.status, "checked_in", "check_in", staff.name)
    order.status = "checked_in"
    db.commit()
    return {"code": 0, "order_no": order.order_no, "status": order.status}


@router.post("/orders/{order_id}/complete")
def complete_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """服务完成：checked_in/in_service -> completed。"""
    staff = _current_staff(authorization, db)
    _require_manager_staff(staff)
    order = _owned_order(db, order_id, staff)
    if order.status not in ("checked_in", "in_service"):
        raise HTTPException(status_code=400, detail=f"当前状态({order.status})不可完成")
    _record_event(db, order.id, order.status, "completed", "complete", staff.name)
    order.status = "completed"
    db.commit()
    return {"code": 0, "order_no": order.order_no, "status": order.status}


@router.get("/orders")
def admin_orders(
    status: str | None = None,
    date: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """订单查询（可按状态/日期过滤）。"""
    staff = _current_staff(authorization, db)
    _require_manager_staff(staff)
    store_id = _staff_store_id(staff)
    stmt = select(Order).where(Order.store_id == store_id).order_by(Order.id.desc()).limit(100)
    if status:
        stmt = stmt.where(Order.status == status)
    if date:
        stmt = stmt.where(Order.booking_date == date)
    orders = list(db.scalars(stmt))
    return {"items": [_order_summary(o) for o in orders], "total": len(orders)}


@router.get("/analytics")
def admin_analytics(
    days: int = 7,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """行为看板：转化漏斗 / 项目热度 / 近期错误 / 每日访问（按天）。"""
    staff = _require_admin(authorization, db)
    store_id = _staff_store_id(staff)
    from sqlalchemy import func

    days = max(1, min(days, 30))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 1. 到店 DIY 主路径漏斗：浏览 -> 看项目 -> 保存配置 -> 提交前台 -> 完成评价。
    # 不再使用旧的线上下单/支付事件，避免后台把线下结算门店误导成支付漏斗。
    funnel = {}
    for ev in ("diy_entry_view", "project_view", "project_config_save", "selection_submit_success", "feedback_submit_success"):
        funnel[ev] = db.scalar(select(func.count()).select_from(EventLog).where(
            EventLog.event == ev, EventLog.store_id == store_id, EventLog.created_at >= since
        )) or 0

    # 2. 项目热度（Python 聚合，量级小、简单可靠）
    view_events = list(db.scalars(select(EventLog).where(
        EventLog.event == "project_view", EventLog.store_id == store_id, EventLog.created_at >= since
    ).limit(3000)))
    pid_counter: Counter = Counter(
        (ev.data or {}).get("project_id") for ev in view_events if (ev.data or {}).get("project_id")
    )
    from app.models import Project
    hot_projects = []
    for pid, cnt in pid_counter.most_common(5):
        proj = db.scalar(select(Project).where(Project.id == int(pid), Project.store_id == store_id))
        if proj is None:
            continue
        hot_projects.append({
            "project_id": int(pid),
            "name": proj.name,
            "views": cnt,
        })

    # 3. 近期错误（近 24h，按信息聚合 Top + 最新 5 条）
    err_since = datetime.now(timezone.utc) - timedelta(hours=24)
    err_events = list(db.scalars(select(EventLog).where(
        EventLog.event == "error", EventLog.store_id == store_id, EventLog.created_at >= err_since
    ).order_by(EventLog.id.desc()).limit(500)))
    err_counter: Counter = Counter(
        ((ev.data or {}).get("type", "unknown"), str((ev.data or {}).get("message", ""))[:60])
        for ev in err_events
    )
    errors = [{"type": k[0], "message": k[1], "count": v} for k, v in err_counter.most_common(8)]
    latest_errors = [{
        "type": (ev.data or {}).get("type", ""),
        "message": str((ev.data or {}).get("message", ""))[:120],
        "path": (ev.data or {}).get("path", ""),
        "ts": ev.created_at.isoformat() if ev.created_at else "",
    } for ev in err_events[:5]]

    # 4. 每日访问（上海时区自然日）
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        day_expr = func.date(EventLog.created_at.op("AT TIME ZONE")("Asia/Shanghai"))
    else:
        day_expr = func.date(EventLog.created_at)
    daily = db.execute(
        select(day_expr, func.count())
        .where(EventLog.event == "diy_entry_view", EventLog.created_at >= since)
        .where(EventLog.store_id == store_id)
        .group_by(day_expr)
        .order_by(day_expr)
    ).all()
    daily_views = [{"date": str(d), "count": c} for d, c in daily]

    return {
        "days": days,
        "funnel": funnel,
        "hot_projects": hot_projects,
        "errors": errors,
        "latest_errors": latest_errors,
        "daily_views": daily_views,
    }


# ============ 券管理（营销配置，限 admin 角色） ============

class CouponTemplateIn(BaseModel):
    code: str = ""
    name: str
    coupon_type: str = "fixed"          # fixed / percent
    amount_cents: int = 0
    percent_off: int | None = None
    min_spend_cents: int = 0
    validity_days: int = 30
    auto_grant_new_user: bool = False
    is_claimable: bool = False
    claim_limit: int = 1
    daily_claimable: bool = False
    auto_apply: bool = False
    status: str = "draft"               # draft / published / archived


class CouponTemplateUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    coupon_type: str | None = None
    amount_cents: int | None = None
    percent_off: int | None = None
    min_spend_cents: int | None = None
    validity_days: int | None = None
    auto_grant_new_user: bool | None = None
    is_claimable: bool | None = None
    claim_limit: int | None = None
    daily_claimable: bool | None = None
    auto_apply: bool | None = None
    status: str | None = None


def _require_admin(authorization: str | None, db: Session) -> Staff:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "需要店长权限"})
    return staff


def _require_manager_staff(staff: Staff) -> Staff:
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "需要店长权限"})
    return staff


def _coupon_out(t: CouponTemplate) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "coupon_type": t.coupon_type,
        "amount_cents": t.amount_cents,
        "percent_off": t.percent_off,
        "min_spend_cents": t.min_spend_cents,
        "validity_days": t.validity_days,
        "auto_grant_new_user": t.auto_grant_new_user,
        "is_claimable": t.is_claimable,
        "claim_limit": t.claim_limit,
        "daily_claimable": t.daily_claimable,
        "auto_apply": t.auto_apply,
        "status": t.status,
    }


@router.get("/coupons")
def admin_coupons(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """券模板列表（营销配置）。"""
    staff = _require_admin(authorization, db)
    store_id = _staff_store_id(staff)
    tpls = list(db.scalars(select(CouponTemplate).where(CouponTemplate.store_id == store_id).order_by(CouponTemplate.id)))
    return {"items": [_coupon_out(t) for t in tpls], "total": len(tpls)}


@router.post("/coupons")
def admin_create_coupon(
    body: CouponTemplateIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """新建券模板。"""
    staff = _require_admin(authorization, db)
    store_id = _staff_store_id(staff)
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请填写券编码")
    if db.scalar(select(CouponTemplate).where(CouponTemplate.store_id == store_id, CouponTemplate.code == code)):
        raise HTTPException(status_code=400, detail="券编码已存在")
    tpl = CouponTemplate(**body.model_dump(exclude={"code"}), code=code, store_id=store_id)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return {"code": 0, "data": _coupon_out(tpl)}


@router.post("/coupons/{tpl_id}")
def admin_update_coupon(
    tpl_id: int,
    body: CouponTemplateUpdate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """更新券模板（含上下架：status 置 published/draft/archived）。"""
    staff = _require_admin(authorization, db)
    store_id = _staff_store_id(staff)
    tpl = db.scalar(select(CouponTemplate).where(CouponTemplate.id == tpl_id, CouponTemplate.store_id == store_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="券不存在")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    if body.code and body.code != tpl.code:
        if db.scalar(select(CouponTemplate).where(
                CouponTemplate.store_id == store_id,
                CouponTemplate.code == body.code, CouponTemplate.id != tpl_id)):
            raise HTTPException(status_code=400, detail="券编码已存在")
    for k, v in data.items():
        setattr(tpl, k, v)
    db.commit()
    return {"code": 0, "data": _coupon_out(tpl)}


def _order_summary(o: Order) -> dict:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "order_type": o.order_type,
        "status": o.status,
        "pay_status": o.pay_status,
        "refund_status": o.refund_status,
        "pay_amount_cents": o.pay_amount_cents,
        "items": o.items,
        "booking_date": o.booking_date,
        "booking_time": o.booking_time,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
