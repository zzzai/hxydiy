"""管理后台 API（HXYOS 第一块）：员工登录、今日预约、订单核销、行为看板。

- 员工账号由 seed 创建（初始密码随机生成，见服务器 admin-credentials.txt）
- 状态机：paid/confirmed -> checked_in(核销) -> completed
"""

import hashlib
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import EventLog, Order, OrderEvent, Staff, User

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


def create_staff_token(staff_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=12)
    payload = {"sub": str(staff_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _current_staff(authorization: str | None, db: Session) -> Staff:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = jwt.decode(authorization[7:], settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="登录已过期")
    staff = db.get(Staff, int(payload["sub"]))
    if not staff or staff.status != "active":
        raise HTTPException(status_code=401, detail="账号不可用")
    return staff


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
    return {
        "token": create_staff_token(staff.id, staff.role),
        "staff": {"id": staff.id, "name": staff.name, "role": staff.role},
    }


@router.get("/today-appointments")
def today_appointments(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """今日预约（已支付/已确认/已核销，按预约时间排序）。"""
    _current_staff(authorization, db)
    today = datetime.now().date().isoformat()
    orders = list(db.scalars(select(Order).where(
        Order.booking_date == today,
        Order.status.in_(["paid", "confirmed", "checked_in", "in_service"]),
    ).order_by(Order.booking_time)))
    return {"date": today, "items": [_order_summary(o) for o in orders], "total": len(orders)}


@router.get("/stats")
def admin_stats(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """经营统计：今日订单/营业额/待核销/访问量/新增用户。"""
    _current_staff(authorization, db)
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=now.hour, minutes=now.minute,
                                seconds=now.second, microseconds=now.microsecond)

    orders_today = list(db.scalars(select(Order).where(Order.created_at >= day_start)))
    paid_today = [o for o in orders_today if o.pay_status == "paid"]
    valid_today = [o for o in orders_today if o.status not in ("cancelled", "expired")]

    pending_checkin = len(list(db.scalars(select(Order).where(
        Order.status.in_(["paid", "confirmed"])
    ))))

    from app.models import EventLog, User
    page_views = len(list(db.scalars(select(EventLog).where(
        EventLog.event == "page_view", EventLog.created_at >= day_start
    ))))
    new_users = len(list(db.scalars(select(User).where(User.created_at >= day_start))))

    return {
        "date": now.date().isoformat(),
        "orders_count": len(valid_today),
        "paid_amount_cents": sum(o.pay_amount_cents for o in paid_today),
        "paid_count": len(paid_today),
        "pending_checkin": pending_checkin,
        "page_views": page_views,
        "new_users": new_users,
    }


@router.post("/orders/{order_id}/check-in")
def check_in_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """到店核销：paid/confirmed -> checked_in。"""
    staff = _current_staff(authorization, db)
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
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
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
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
    _current_staff(authorization, db)
    stmt = select(Order).order_by(Order.id.desc()).limit(100)
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
    _current_staff(authorization, db)
    from sqlalchemy import func

    days = max(1, min(days, 30))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 1. 转化漏斗
    funnel = {}
    for ev in ("page_view", "project_view", "add_cart", "create_order", "pay_click"):
        funnel[ev] = db.scalar(select(func.count()).select_from(EventLog).where(
            EventLog.event == ev, EventLog.created_at >= since
        )) or 0

    # 2. 项目热度（Python 聚合，量级小、简单可靠）
    view_events = list(db.scalars(select(EventLog).where(
        EventLog.event == "project_view", EventLog.created_at >= since
    ).limit(3000)))
    pid_counter: Counter = Counter(
        (ev.data or {}).get("project_id") for ev in view_events if (ev.data or {}).get("project_id")
    )
    from app.models import Project
    hot_projects = []
    for pid, cnt in pid_counter.most_common(5):
        proj = db.get(Project, int(pid))
        hot_projects.append({
            "project_id": int(pid),
            "name": proj.name if proj else f"项目#{pid}",
            "views": cnt,
        })

    # 3. 近期错误（近 24h，按信息聚合 Top + 最新 5 条）
    err_since = datetime.now(timezone.utc) - timedelta(hours=24)
    err_events = list(db.scalars(select(EventLog).where(
        EventLog.event == "error", EventLog.created_at >= err_since
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
    tz_expr = EventLog.created_at.op("AT TIME ZONE")("Asia/Shanghai")
    daily = db.execute(
        select(func.date(tz_expr), func.count())
        .where(EventLog.event == "page_view", EventLog.created_at >= since)
        .group_by(func.date(tz_expr))
        .order_by(func.date(tz_expr))
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


def _order_summary(o: Order) -> dict:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "order_type": o.order_type,
        "status": o.status,
        "pay_amount_cents": o.pay_amount_cents,
        "items": o.items,
        "booking_date": o.booking_date,
        "booking_time": o.booking_time,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
