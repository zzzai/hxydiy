"""支付模块：微信支付 v3 JSAPI 下单 + 回调（公钥模式验签）。

状态机：pending_payment -> paid（回调到达）-> confirmed（预约确认）
幂等：回调按 out_trade_no 幂等，重复通知不重复改状态；事件全部落 order_events。
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Order, OrderEvent, User
from app.services.wechatpay import (
    WechatPayError, create_jsapi_payment, verify_and_decrypt_notify,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def _record_event(db: Session, order_id: int, from_status: str, to_status: str,
                  action: str, operator: str, reason: str = "") -> None:
    db.add(OrderEvent(
        order_id=order_id, from_status=from_status, to_status=to_status,
        action=action, operator=operator, reason=reason,
    ))


@router.post("/{order_id}/pay")
async def create_payment(
    order_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """创建微信支付：校验订单归属/状态 -> JSAPI 下单 -> 返回调起参数。"""
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization[7:])
        if payload:
            user_id = int(payload["sub"])
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    order = db.get(Order, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.pay_status == "paid":
        raise HTTPException(status_code=400, detail="订单已支付")
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail="当前订单状态不支持支付")

    # 30 分钟未支付自动过期
    from datetime import datetime, timezone
    if order.expire_at and datetime.now(timezone.utc) > order.expire_at:
        _record_event(db, order.id, order.status, "expired", "expire", "system",
                      "支付超时自动过期")
        order.status = "expired"
        db.commit()
        raise HTTPException(status_code=400, detail="订单已过期，请重新下单")

    user = db.get(User, order.user_id)
    try:
        pay_params = await create_jsapi_payment(
            out_trade_no=order.order_no,
            description="荷小悦-服务预约",
            amount_cents=order.pay_amount_cents,
            openid=user.openid if user else "",
        )
    except WechatPayError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"code": 0, "data": pay_params}


@router.post("/notify")
async def pay_notify(request: Request, db: Session = Depends(get_db)) -> dict:
    """微信支付结果回调：验签 -> 解密 -> 幂等更新订单状态。"""
    raw_body = await request.body()
    try:
        payload = await verify_and_decrypt_notify(dict(request.headers), raw_body)
    except WechatPayError as e:
        raise HTTPException(status_code=401, detail=str(e))

    trade_state = payload.get("trade_state", "")
    out_trade_no = payload.get("out_trade_no", "")
    transaction_id = payload.get("transaction_id", "")

    order = db.scalar(select(Order).where(Order.order_no == out_trade_no))
    if not order:
        # 无法识别的订单号也返回成功，避免微信重试风暴
        return {"code": "SUCCESS", "message": "成功"}

    if trade_state == "SUCCESS" and order.pay_status != "paid":
        if order.status == "cancelled":
            # 已取消订单收到迟到的成功回调：不改状态，仅记录审计事件。
            _record_event(db, order.id, order.status, order.status, "pay_callback",
                          "wechat", f"txn={transaction_id}, ignored: order cancelled")
            db.commit()
            return {"code": "SUCCESS", "message": "成功"}
        _record_event(
            db, order.id, order.status, "paid", "pay_callback", "wechat",
            f"txn={transaction_id}",
        )
        order.status = "paid"
        order.pay_status = "paid"
        order.pay_transaction_id = transaction_id
        # 券生命周期闭环：支付成功后锁定券转 used 并回填使用订单。
        if order.coupon_id:
            from app.models import UserCoupon
            uc = db.get(UserCoupon, order.coupon_id)
            if uc and uc.status == "locked":
                uc.status = "used"
                uc.used_order_id = order.id
        db.commit()
    elif trade_state in ("CLOSED", "REVOKED", "PAYERROR") and order.pay_status != "paid":
        _record_event(db, order.id, order.status, "cancelled", "pay_callback",
                      "wechat", f"trade_state={trade_state}")
        order.status = "cancelled"
        # 释放锁定的优惠券，与下单锁定逻辑对称。
        if order.coupon_id:
            from app.models import UserCoupon
            uc = db.get(UserCoupon, order.coupon_id)
            if uc and uc.status == "locked":
                uc.status = "unused"
        db.commit()

    return {"code": "SUCCESS", "message": "成功"}
