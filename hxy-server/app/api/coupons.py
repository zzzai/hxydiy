"""优惠券模块：我的券列表、领券中心、每日领券、分享有礼。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import CouponTemplate, User, UserCoupon, SelectionSession

router = APIRouter(prefix="/coupons", tags=["coupons"])

SHARE_COUPON_CODE = "share-gift-300"   # 分享有礼券（24h 限 1 次）


def _aware(value):
    """SQLite 读出 naive datetime 时归一化为 UTC，与 Postgres 行为一致。"""
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _user_id(authorization: str | None) -> int | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    return int(payload["sub"]) if payload else None

def _trusted_store_id(db: Session, user: User | None) -> int | None:
    if not user:
        return None
    if user.membership_store_id:
        return user.membership_store_id
    return db.scalar(select(SelectionSession.store_id).where(
        SelectionSession.customer_id == user.id,
        SelectionSession.store_id.is_not(None),
    ).order_by(SelectionSession.created_at.desc()).limit(1))

def _template_allowed(tpl: CouponTemplate, store_id: int | None) -> bool:
    return tpl.store_id is None or (store_id is not None and tpl.store_id == store_id)


def _template_out(tpl: CouponTemplate, claimed_today: bool, claimed_total: int) -> dict:
    """领券中心模板展示：带领取状态（每日/总额）"""
    if tpl.daily_claimable:
        claimable = not claimed_today
        note = "每日可领 1 张" if claimable else "今日已领"
    else:
        claimable = tpl.claim_limit <= 0 or claimed_total < tpl.claim_limit
        note = "" if claimable else "已达领取上限"
    return {
        "id": tpl.id,
        "name": tpl.name,
        "coupon_type": tpl.coupon_type,
        "amount_cents": tpl.amount_cents,
        "percent_off": tpl.percent_off,
        "min_spend_cents": tpl.min_spend_cents,
        "validity_days": tpl.validity_days,
        "daily_claimable": tpl.daily_claimable,
        "claimable": claimable,
        "note": note,
    }


@router.get("/templates")
def claimable_templates(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """领券中心：可公开领取的券模板（无需登录可看，领取需登录）。"""
    user_id = _user_id(authorization)
    user = db.get(User, user_id) if user_id is not None else None
    if user_id is not None:
        if user and user.is_member:
            return {"items": [], "total": 0}
    templates = list(db.scalars(select(CouponTemplate).where(
        CouponTemplate.is_claimable.is_(True),
        CouponTemplate.status == "published",
    )))
    trusted_store_id = _trusted_store_id(db, user)
    templates = [tpl for tpl in templates if _template_allowed(tpl, trusted_store_id)]
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=now.hour, minutes=now.minute,
                                seconds=now.second, microseconds=now.microsecond)

    items = []
    for tpl in templates:
        if user_id is None:
            items.append(_template_out(tpl, claimed_today=False, claimed_total=0))
            continue
        claimed = list(db.scalars(select(UserCoupon).where(
            UserCoupon.user_id == user_id, UserCoupon.template_id == tpl.id
        )))
        claimed_today = any(c.claimed_at and c.claimed_at >= day_start for c in claimed)
        items.append(_template_out(tpl, claimed_today, len(claimed)))
    return {"items": items, "total": len(items)}


@router.get("/activity")
def activity_promotion(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """全场满减活动（结算页展示）：取 auto_apply 模板中最高面额。

    会员直接享会员最低价，不展示非会员券活动。
    """
    user_id = _user_id(authorization)
    user = db.get(User, user_id) if user_id is not None else None
    if user_id is not None:
        if user and user.is_member:
            return {"items": [], "total": 0}
    tpls = list(db.scalars(select(CouponTemplate).where(
        CouponTemplate.auto_apply.is_(True), CouponTemplate.status == "published"
    )))
    tpls = [tpl for tpl in tpls if _template_allowed(tpl, _trusted_store_id(db, user))]
    items = [{
        "id": t.id,
        "name": t.name,
        "coupon_type": t.coupon_type,
        "amount_cents": t.amount_cents,
        "percent_off": t.percent_off,
        "min_spend_cents": t.min_spend_cents,
    } for t in sorted(tpls, key=lambda x: x.amount_cents or 0, reverse=True)]
    return {"items": items, "total": len(items)}


class ClaimRequest(BaseModel):
    template_id: int


@router.post("/claim")
def claim_coupon(
    body: ClaimRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """领取领券中心券（服务端校验：可领 / 每日限领 / 总限领）。"""
    user_id = _user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先完成手机号登录")
    user = db.get(User, user_id)
    if user and user.is_member:
        raise HTTPException(status_code=400, detail="会员已享会员价，无需领取优惠券")
    # 锁用户行：同一顾客的并发领券串行化，防止重复突破限领。
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    tpl = db.get(CouponTemplate, body.template_id)
    if not tpl or not tpl.is_claimable or tpl.status != "published" or not _template_allowed(tpl, _trusted_store_id(db, user)):
        raise HTTPException(status_code=404, detail="券不存在或不可领取")

    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=now.hour, minutes=now.minute,
                                seconds=now.second, microseconds=now.microsecond)
    claimed = list(db.scalars(select(UserCoupon).where(
        UserCoupon.user_id == user_id, UserCoupon.template_id == tpl.id
    )))
    if tpl.daily_claimable:
        if any(c.claimed_at and _aware(c.claimed_at) >= day_start for c in claimed):
            raise HTTPException(status_code=400, detail="今日已领取，明天再来")
    else:
        if tpl.claim_limit > 0 and len(claimed) >= tpl.claim_limit:
            raise HTTPException(status_code=400, detail="已达领取上限")

    db.add(UserCoupon(
        user_id=user_id,
        template_id=tpl.id,
        status="unused",
        expire_at=now + timedelta(days=tpl.validity_days),
    ))
    db.commit()
    return {"code": 0, "name": tpl.name}


@router.post("/claim-share")
def claim_share_coupon(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """分享有礼：分享小程序得券（24h 内同用户限 1 次，幂等）。"""
    user_id = _user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get(User, user_id)
    if user and user.is_member:
        return {"code": 0, "granted": False, "reason": "会员已享会员价，无需领取优惠券"}
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    tpl = db.scalar(select(CouponTemplate).where(CouponTemplate.code == SHARE_COUPON_CODE))
    if not tpl or tpl.status != "published" or not _template_allowed(tpl, _trusted_store_id(db, user)):
        return {"code": 0, "granted": False, "reason": "分享券未配置"}

    now = datetime.now(timezone.utc)
    recent = db.scalar(select(UserCoupon).where(
        UserCoupon.user_id == user_id,
        UserCoupon.template_id == tpl.id,
        UserCoupon.claimed_at >= now - timedelta(hours=24),
    ))
    if recent:
        return {"code": 0, "granted": False, "reason": "24h 内已领取"}

    db.add(UserCoupon(
        user_id=user_id,
        template_id=tpl.id,
        status="unused",
        expire_at=now + timedelta(days=tpl.validity_days),
    ))
    db.commit()
    return {"code": 0, "granted": True, "name": tpl.name}


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
    trusted_store_id = _trusted_store_id(db, db.get(User, user_id))
    if trusted_store_id is not None:
        stmt = stmt.where((CouponTemplate.store_id == trusted_store_id) | CouponTemplate.store_id.is_(None))
    else:
        stmt = stmt.where(CouponTemplate.store_id.is_(None))
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
