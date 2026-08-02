"""管理后台 API（HXYOS 第一块）：员工登录、今日预约、订单核销。

- 员工账号由 seed 创建（初始密码随机生成，见服务器 admin-credentials.txt）
- 状态机：paid/confirmed -> checked_in(核销) -> completed
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Order, OrderEvent, Staff, User

router = APIRouter(prefix="/admin", tags=["admin"])

PBKDF2_ITERATIONS = 120_000


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
    staff = db.scalar(select(Staff).where(Staff.username == username))
    if not staff or staff.status != "active" or not verify_password(password, staff.password_hash):
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
