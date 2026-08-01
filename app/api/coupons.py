"""优惠券模块：我的券列表（含动态过期状态）。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import CouponTemplate, UserCoupon

router = APIRouter(prefix="/coupons", tags=["coupons"])


def _user_id(authorization: str | None) -> int | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    return int(payload["sub"]) if payload else None


@router.get("")
def my_coupons(
    status: str | None = None,  # unused / used / expired / locked
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """我的优惠券列表（合并模板信息；unused 且过期的动态标记为 expired）。"""
    user_id = _user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    stmt = (
        select(UserCoupon, CouponTemplate)
        .join(CouponTemplate, UserCoupon.template_id == CouponTemplate.id)
        .where(UserCoupon.user_id == user_id)
    )
    rows = db.execute(stmt).all()
    now = datetime.now(timezone.utc)

    items = []
    for uc, tpl in rows:
        c_status = uc.status
        if c_status == "unused" and uc.expire_at and uc.expire_at < now:
            c_status = "expired"
        if status and c_status != status:
            continue
        items.append({
            "id": uc.id,
            "name": tpl.name,
            "coupon_type": tpl.coupon_type,
            "amount_cents": tpl.amount_cents,
            "percent_off": tpl.percent_off,
            "min_spend_cents": tpl.min_spend_cents,
            "status": c_status,
            "claimed_at": uc.claimed_at.isoformat() if uc.claimed_at else None,
            "expire_at": uc.expire_at.isoformat() if uc.expire_at else None,
        })

    items.sort(key=lambda x: 0 if x["status"] == "unused" else 1)
    return {"items": items, "total": len(items)}
