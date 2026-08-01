"""订单模块：服务端计价（不信任前端）、状态机、审计事件。

移植自云函数 createOrder，价格一律从 price_book/addons 读取。
状态机见 app/models/orders.py 顶部注释。
"""

import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Order, OrderEvent, PriceBook, Project, Store, User, UserCoupon
from app.schemas.order import CreateOrderResponse, OrderCreate, OrderOut
from app.core.security import decode_token
from fastapi import Header

router = APIRouter(prefix="/orders", tags=["orders"])

PAYMENT_TIMEOUT_MINUTES = 30


def _current_user_id(authorization: str | None = Header(default=None)) -> int | None:
    """从 Bearer token 取用户 ID；游客返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    return int(payload["sub"]) if payload else None


def gen_order_no() -> str:
    ymd = datetime.now().strftime("%Y%m%d")
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"HXY{ymd}{rand}"


def _record_event(db: Session, order_id: int, from_status: str, to_status: str,
                  action: str, operator: str, reason: str = "") -> None:
    db.add(OrderEvent(
        order_id=order_id, from_status=from_status, to_status=to_status,
        action=action, operator=operator, reason=reason,
    ))


@router.post("", response_model=CreateOrderResponse)
def create_order(
    body: OrderCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CreateOrderResponse:
    """下单：服务端按价格表计价，生成 pending_payment 订单。"""
    user_id = _current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not db.get(Store, body.store_id):
        raise HTTPException(status_code=404, detail="门店不存在")

    total_cents = 0
    discount_cents = 0
    order_items: list[dict] = []

    for item in body.items:
        project = db.get(Project, item.project_id)
        if not project or project.publication_status != "published":
            raise HTTPException(status_code=404, detail=f"项目 {item.project_id} 不存在或未发布")

        # 服务端读价：会员取 member 价，否则取 store 价
        price_row = db.scalar(select(PriceBook).where(
            PriceBook.project_id == project.id,
            PriceBook.price_type == ("member" if user.is_member else "store"),
        ))
        if price_row is None:
            price_row = db.scalar(select(PriceBook).where(
                PriceBook.project_id == project.id, PriceBook.price_type == "store"
            ))
        unit_price = price_row.amount_cents if price_row else 0

        addon_price = 0
        for addon_id in item.addon_ids:
            from app.models import Addon
            addon = db.get(Addon, addon_id)
            if addon and addon.publication_status == "published":
                addon_price += addon.price_cents

        subtotal = (unit_price + addon_price) * item.quantity
        total_cents += subtotal
        order_items.append({
            "project_id": project.id,
            "name": project.name,
            "unit_price_cents": unit_price,
            "addon_price_cents": addon_price,
            "quantity": item.quantity,
            "subtotal_cents": subtotal,
        })

    # 优惠券锁定（支付成功后变 used，失败/过期释放）
    if body.coupon_id:
        coupon = db.get(UserCoupon, body.coupon_id)
        if coupon and coupon.user_id == user.id and coupon.status == "unused":
            from app.models import CouponTemplate
            tpl = db.get(CouponTemplate, coupon.template_id)
            if tpl and total_cents >= tpl.min_spend_cents:
                discount_cents = tpl.amount_cents
                coupon.status = "locked"

    pay_amount = max(total_cents - discount_cents, 0)

    order = Order(
        order_no=gen_order_no(),
        order_type=body.order_type,
        user_id=user.id,
        store_id=body.store_id,
        items=order_items,
        booking_date=body.booking_date,
        booking_time=body.booking_time,
        coupon_id=body.coupon_id,
        total_amount_cents=total_cents,
        discount_cents=discount_cents,
        pay_amount_cents=pay_amount,
        status="pending_payment",
        pay_status="unpaid",
        expire_at=datetime.now(timezone.utc) + timedelta(minutes=PAYMENT_TIMEOUT_MINUTES),
    )
    db.add(order)
    db.flush()
    _record_event(db, order.id, "draft", "pending_payment", "create", f"user:{user.id}")
    db.commit()
    db.refresh(order)
    return CreateOrderResponse(data=OrderOut.model_validate(order))


@router.get("", response_model=list[OrderOut])
def list_orders(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[Order]:
    user_id = _current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return list(db.scalars(
        select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(50)
    ))


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Order:
    user_id = _current_user_id(authorization)
    order = db.get(Order, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order
