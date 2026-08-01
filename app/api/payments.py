from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Order, OrderEvent

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/{order_id}/pay")
def create_payment(order_id: int, db: Session = Depends(get_db)) -> dict:
    """微信支付 v3 JSAPI 下单 —— 待实现（Task: 微信支付 v3 对接）。

    规划：校验订单归属与状态 -> 构造 JSAPI 下单请求 -> 返回小程序端调起参数。
    验签采用微信支付公钥模式（官方推荐，无过期时间）。
    """
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    raise HTTPException(status_code=501, detail="支付接口待接入（开发中）")


@router.post("/notify")
async def pay_notify() -> dict:
    """微信支付回调 —— 待实现。"""
    raise HTTPException(status_code=501, detail="支付回调待接入（开发中）")
