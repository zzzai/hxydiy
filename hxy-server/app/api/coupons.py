"""优惠券模块：我的券列表、领券中心、每日领券、分享有礼。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.customer_auth import current_customer_id
from app.core.config import settings
from app.db.session import get_db
from app.domain.coupon_issuance import coupon_budget_exhausted, lock_coupon_template, try_issue_coupon
from app.domain.coupon_redeem import create_redeem_token, decode_claim_token
from app.models import AuditLog, CouponTemplate, User, UserCoupon, SelectionSession

router = APIRouter(prefix="/coupons", tags=["coupons"])

SHARE_COUPON_CODE = "share-gift-300"   # 分享有礼券（24h 限 1 次）


def _aware(value):
    """SQLite 读出 naive datetime 时归一化为 UTC，与 Postgres 行为一致。"""
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _user_id(authorization: str | None, db: Session) -> int | None:
    return current_customer_id(authorization, db, optional=True)

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
    if not settings.coupon_issuance_enabled:
        return {"items": [], "total": 0}
    user_id = _user_id(authorization, db)
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
    user_id = _user_id(authorization, db)
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
    user_id = _user_id(authorization, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先完成手机号登录")
    if not settings.coupon_issuance_enabled:
        raise HTTPException(status_code=409, detail={"code": "COUPON_ISSUANCE_PAUSED", "message": "领券活动已暂停"})
    user = db.get(User, user_id)
    if user and user.is_member:
        raise HTTPException(status_code=400, detail="会员已享会员价，无需领取优惠券")
    # 锁用户行：同一顾客的并发领券串行化，防止重复突破限领。
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    tpl = lock_coupon_template(db, CouponTemplate.id == body.template_id)
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

    if try_issue_coupon(db, tpl, user_id, now + timedelta(days=tpl.validity_days)) is None:
        raise coupon_budget_exhausted()
    db.commit()
    return {"code": 0, "name": tpl.name}


@router.post("/claim-share")
def claim_share_coupon(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """分享有礼：分享小程序得券（24h 内同用户限 1 次，幂等）。"""
    if not settings.coupon_issuance_enabled:
        return {"code": 0, "granted": False, "reason": "领券活动已暂停"}
    user_id = _user_id(authorization, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get(User, user_id)
    if user and user.is_member:
        return {"code": 0, "granted": False, "reason": "会员已享会员价，无需领取优惠券"}
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    tpl = lock_coupon_template(db, CouponTemplate.code == SHARE_COUPON_CODE)
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

    if try_issue_coupon(db, tpl, user_id, now + timedelta(days=tpl.validity_days)) is None:
        return {"code": 0, "granted": False, "reason": "券预算不足，不能继续发放"}
    db.commit()
    return {"code": 0, "granted": True, "name": tpl.name}


@router.get("")
def my_coupons(
    status: str | None = None,  # unused / used / expired / locked
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """我的优惠券列表（合并模板信息；unused 且过期的动态标记为 expired）。"""
    user_id = _user_id(authorization, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    stmt = (
        select(UserCoupon, CouponTemplate)
        .join(CouponTemplate, UserCoupon.template_id == CouponTemplate.id)
        .where(UserCoupon.user_id == user_id)
    )
    # Coupons are user-owned. A manager may issue a store coupon to a WeChat
    # contact who has no order/store history yet; do not hide it behind the
    # trusted-store filter.
    rows = db.execute(stmt).all()
    now = datetime.now(timezone.utc)

    items = []
    for uc, tpl in rows:
        c_status = uc.status
        if c_status == "unused" and uc.expire_at and _aware(uc.expire_at) < now:
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


class ClaimHalfPriceIn(BaseModel):
    code: str | None = None
    token: str | None = None


@router.post("/claim-half-price")
def claim_half_price(
    body: ClaimHalfPriceIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """通过店长分享的链接/二维码领取半价券；同一顾客最多一张。"""
    user_id = _user_id(authorization, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    value = (body.code or body.token or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail={"code": "COUPON_LINK_INVALID", "message": "领券链接无效或已过期"})
    payload = decode_claim_token(value)
    template = lock_coupon_template(
        db, CouponTemplate.id == payload["template_id"],
        CouponTemplate.store_id == payload["store_id"],
    )
    if not template or template.status != "published":
        raise HTTPException(status_code=404, detail={"code": "COUPON_LINK_INVALID", "message": "领券活动不存在或已结束"})
    issued = int(db.scalar(select(func.count()).select_from(UserCoupon).where(
        UserCoupon.template_id == template.id,
    )) or 0)
    if issued >= 100:
        raise HTTPException(status_code=409, detail={"code": "COUPON_SOLD_OUT", "message": "半价券 100 张已发完"})
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    existing = db.scalar(select(UserCoupon.id).where(
        UserCoupon.user_id == user_id,
        UserCoupon.template_id == template.id,
        UserCoupon.status == "unused",
    ))
    if existing:
        raise HTTPException(status_code=409, detail={"code": "COUPON_ALREADY_HELD", "message": "你已经有一张未使用的半价券"})
    now = datetime.now(timezone.utc)
    coupon = try_issue_coupon(
        db, template, user_id, now + timedelta(days=template.validity_days or 60),
        claimed_at=now,
    )
    if coupon is None:
        raise coupon_budget_exhausted()
    db.add(AuditLog(
        actor_type="customer", actor_id=str(user_id),
        action="customer_claim_half_price_coupon", entity_type="user_coupon",
        entity_id=str(coupon.id), store_id=template.store_id,
        detail={"template_id": template.id, "template_code": template.code, "link_claim": True},
    ))
    db.commit()
    return {
        "coupon_id": coupon.id,
        "name": template.name,
        "percent_off": template.percent_off,
        "expire_at": coupon.expire_at.isoformat(),
        "remaining": max(0, 100 - issued - 1),
    }


@router.post("/{coupon_id}/redeem-token")
def coupon_redeem_token(
    coupon_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """顾客生成一次性核销码；只返回给券本人，已使用/过期/锁定券拒绝。"""
    user_id = _user_id(authorization, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    coupon = db.scalar(select(UserCoupon).where(
        UserCoupon.id == coupon_id,
        UserCoupon.user_id == user_id,
    ))
    if not coupon:
        raise HTTPException(status_code=404, detail={"code": "COUPON_NOT_FOUND", "message": "券不存在"})
    now = datetime.now(timezone.utc)
    if coupon.status == "used":
        raise HTTPException(status_code=409, detail={"code": "COUPON_ALREADY_USED", "message": "该券已核销"})
    if coupon.status != "unused":
        raise HTTPException(status_code=409, detail={"code": "COUPON_NOT_REDEEMABLE", "message": "该券当前不可核销"})
    if coupon.expire_at and _aware(coupon.expire_at) <= now:
        raise HTTPException(status_code=409, detail={"code": "COUPON_EXPIRED", "message": "该券已过期"})
    template = db.get(CouponTemplate, coupon.template_id)
    token, expires_at = create_redeem_token(coupon.id, user_id)
    return {
        "coupon_id": coupon.id,
        "name": template.name if template else "优惠券",
        "token": token,
        "expires_at": expires_at.isoformat(),
    }
