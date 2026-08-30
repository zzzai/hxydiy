"""订单模块：服务端计价（不信任前端）、状态机、审计事件。

移植自云函数 createOrder，价格一律从 price_book/addons 读取。
状态机见 app/models/orders.py 顶部注释。
"""

import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
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


INVITE_REWARD_CODE = "invite-reward-500"
INVITE_REWARD_DAILY_LIMIT = 3


def _grant_inviter_reward(db: Session, inviter_id: int) -> bool:
    """邀请人得老带新券（每日限 3 张）。"""
    from app.models import CouponTemplate
    tpl = db.scalar(select(CouponTemplate).where(CouponTemplate.code == INVITE_REWARD_CODE))
    if not tpl or tpl.status != "published":
        return False
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=now.hour, minutes=now.minute,
                                seconds=now.second, microseconds=now.microsecond)
    today_count = len(list(db.scalars(select(UserCoupon).where(
        UserCoupon.user_id == inviter_id, UserCoupon.template_id == tpl.id,
        UserCoupon.claimed_at >= day_start,
    ))))
    if today_count >= INVITE_REWARD_DAILY_LIMIT:
        return False
    db.add(UserCoupon(
        user_id=inviter_id, template_id=tpl.id, status="unused",
        expire_at=now + timedelta(days=tpl.validity_days),
    ))
    return True


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
    if user.is_member and body.coupon_id:
        raise HTTPException(status_code=400, detail="会员已享会员价，无需领取优惠券")

    total_cents = 0
    discount_cents = 0
    order_items: list[dict] = []

    # 会员订单：按 member_plans 计价（年度卡/月卡/储值）
    if body.order_type == "member":
        if not body.member_plan_id:
            raise HTTPException(status_code=400, detail="请选择会员方案")
        from app.models import MemberPlan
        plan = db.get(MemberPlan, body.member_plan_id)
        if not plan or plan.status != "published":
            raise HTTPException(status_code=404, detail="会员方案不存在或未发布")
        total_cents = plan.price_cents
        order_items.append({
            "name": plan.name,
            "unit_price_cents": plan.price_cents,
            "quantity": 1,
            "subtotal_cents": plan.price_cents,
        })
    else:
        for item in body.items:
            project = db.get(Project, item.project_id)
            if not project or project.publication_status != "published":
                raise HTTPException(status_code=404, detail=f"项目 {item.project_id} 不存在或未发布")

            # 服务端读价：会员取 member 价，否则取 store 价
            price_row = db.scalar(
                select(PriceBook)
                .where(
                    PriceBook.project_id == project.id,
                    PriceBook.price_type == ("member" if user.is_member else "store"),
                    or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > datetime.now(timezone.utc)),
                )
                .order_by(PriceBook.published_at.desc(), PriceBook.id.desc())
            )
            if price_row is None:
                price_row = db.scalar(
                    select(PriceBook)
                    .where(
                        PriceBook.project_id == project.id,
                        PriceBook.price_type == "store",
                        or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > datetime.now(timezone.utc)),
                    )
                    .order_by(PriceBook.published_at.desc(), PriceBook.id.desc())
                )
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

    # 优惠券/活动满减（支付成功后变 used，失败/过期释放）；percent 券按折扣率计算
    if body.coupon_id:
        coupon = db.get(UserCoupon, body.coupon_id)
        if coupon and coupon.user_id == user.id and coupon.status == "unused":
            now = datetime.now(timezone.utc)
            if coupon.expire_at and coupon.expire_at.tzinfo is None:
                coupon.expire_at = coupon.expire_at.replace(tzinfo=timezone.utc)
            if coupon.expire_at and coupon.expire_at < now:
                raise HTTPException(status_code=400, detail="优惠券已过期，请重新选择")
            from app.models import CouponTemplate
            tpl = db.get(CouponTemplate, coupon.template_id)
            if tpl and total_cents >= tpl.min_spend_cents:
                if tpl.coupon_type == "percent" and tpl.percent_off:
                    discount_cents = int(total_cents * tpl.percent_off / 100)
                else:
                    discount_cents = tpl.amount_cents
                coupon.status = "locked"
    # 未显式选择优惠券时不在旧订单接口隐式套用全局活动。
    # 选单/前台结算的自动券由 app.domain.automatic_coupon 统一计算，
    # 避免旧接口与生产结算域出现两套价格规则或跨门店串用活动。

    # 邀请裂变：被邀请人首单成功创建 → 邀请人得老带新券（每日限 3 张，防刷）
    if user.inviter_id and body.order_type != "member":
        from app.models import Order as OrderModel
        first_order = not db.scalar(select(OrderModel.id).where(
            OrderModel.user_id == user.id
        ).limit(1))
        if first_order:
            _grant_inviter_reward(db, user.inviter_id)

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


def _lazy_expire(db: Session, order: Order) -> bool:
    """惰性过期：pending_payment 且超过 expire_at -> expired，并释放锁定的优惠券。"""
    from datetime import datetime, timezone
    if order.status == "pending_payment" and order.expire_at:
        if datetime.now(timezone.utc) > order.expire_at:
            _record_event(db, order.id, order.status, "expired", "expire", "system",
                          "支付超时自动过期")
            order.status = "expired"
            if order.coupon_id:
                uc = db.get(UserCoupon, order.coupon_id)
                if uc and uc.status == "locked":
                    uc.status = "unused"
                    uc.locked_order_id = None
            db.commit()
            return True
    return False


@router.get("", response_model=list[OrderOut])
def list_orders(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[Order]:
    user_id = _current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    orders = list(db.scalars(
        select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(50)
    ))
    for o in orders:
        _lazy_expire(db, o)
    return orders


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """顾客自助取消：仅未支付订单可取消，释放锁定的优惠券并记录审计事件。"""
    user_id = _current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    order = db.get(Order, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "cancelled":
        raise HTTPException(status_code=409, detail="订单已取消")
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail="当前订单状态不支持自助取消，请联系门店")
    _record_event(db, order.id, order.status, "cancelled", "cancel", f"user:{user_id}", "顾客主动取消")
    order.status = "cancelled"
    if order.coupon_id:
        uc = db.get(UserCoupon, order.coupon_id)
        if uc and uc.status == "locked":
            uc.status = "unused"
            uc.locked_order_id = None
    db.commit()
    return {"code": 0, "status": "cancelled"}


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
    _lazy_expire(db, order)
    db.refresh(order)
    return order
