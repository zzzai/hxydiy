"""Authenticated first-claim ownership for individual poster offers."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.half_price_coupon import coupon_display_name, coupon_scope
from app.domain.coupon_issuance import coupon_budget_exhausted, lock_coupon_template, try_issue_coupon
from app.models import AuditLog, CouponPosterLink, CouponTemplate, User, UserCoupon


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def poster_error(code: str, message: str, status: int = 409):
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def get_poster(db: Session, payload: dict) -> CouponPosterLink:
    poster = db.get(CouponPosterLink, payload["poster_id"])
    if not poster or poster.store_id != payload["store_id"]:
        raise poster_error("COUPON_LINK_INVALID", "领券链接无效或已过期", 404)
    return poster


def owned_coupon_view(coupon: UserCoupon, template: CouponTemplate) -> dict:
    status = coupon.status
    if status == "unused" and coupon.expire_at and aware(coupon.expire_at) <= datetime.now(UTC):
        status = "expired"
    return {
        "coupon_id": coupon.id, "name": coupon_display_name(template), **coupon_scope(template), "percent_off": template.percent_off,
        "expire_at": aware(coupon.expire_at).isoformat() if coupon.expire_at else None, "status": status,
    }


def poster_status(db: Session, payload: dict, user_id: int | None) -> dict:
    poster = get_poster(db, payload)
    template = db.get(CouponTemplate, poster.template_id)
    if poster.coupon_id:
        coupon = db.get(UserCoupon, poster.coupon_id)
        if coupon and coupon.user_id == user_id:
            return {"state": "owned", "coupon": owned_coupon_view(coupon, template)}
        # Never disclose the recipient's name, phone, ID, or redemption code.
        return {"state": "claimed"}
    if aware(poster.expires_at) <= datetime.now(UTC) or not template or template.status != "published":
        return {"state": "unavailable"}
    return {"state": "available", "validity_days": template.validity_days or 60}


def claim_poster(db: Session, payload: dict, user_id: int) -> dict:
    # Keep the user -> template -> poster lock order across all issuance paths.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user or not user.phone:
        raise poster_error("COUPON_PHONE_REQUIRED", "请验证手机号后领取，优惠券将绑定本人账户", 401)
    source = get_poster(db, payload)
    template = lock_coupon_template(db, CouponTemplate.id == source.template_id)
    poster = db.scalar(select(CouponPosterLink).where(
        CouponPosterLink.id == source.id,
    ).with_for_update().execution_options(populate_existing=True))
    if poster.coupon_id:
        coupon = db.get(UserCoupon, poster.coupon_id)
        if coupon and coupon.user_id == user_id:
            return owned_coupon_view(coupon, template)
        raise poster_error("POSTER_ALREADY_CLAIMED", "这张券已被领取")
    now = datetime.now(UTC)
    if aware(poster.expires_at) <= now or not template or template.status != "published":
        raise poster_error("COUPON_LINK_INVALID", "领券活动不存在或已结束", 404)
    issued = db.scalar(select(func.count()).select_from(UserCoupon).where(
        UserCoupon.template_id == template.id,
    )) or 0
    if issued >= 100:
        raise poster_error("COUPON_SOLD_OUT", "本次活动优惠券已领完")
    coupon = try_issue_coupon(db, template, user.id, now + timedelta(days=template.validity_days or 60), claimed_at=now)
    if coupon is None:
        raise coupon_budget_exhausted()
    poster.coupon_id = coupon.id
    db.add(AuditLog(
        actor_type="customer", actor_id=str(user.id), action="customer_claim_poster_coupon",
        entity_type="user_coupon", entity_id=str(coupon.id), store_id=poster.store_id,
        detail={"poster_id": poster.id, "template_id": template.id},
    ))
    db.commit()
    return owned_coupon_view(coupon, template)
