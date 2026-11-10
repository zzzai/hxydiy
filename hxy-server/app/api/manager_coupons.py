"""Manager-issued half-price coupons and one-time scan redemption.

This is a standalone marketing redemption: it marks the coupon used and does
not mutate an order or payment. The customer QR is a short-lived signed token;
the manager endpoint re-checks the coupon, store and customer on every call.
"""

from datetime import UTC, datetime, timedelta
import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select, update
from sqlalchemy.orm import Session

from app.api.admin import _current_staff
from app.api.admin_v2 import (
    _audit,
    _customer_display_name,
    _masked_phone,
    _require_admin,
    _resolve_target_store_id,
    _store_user_ids,
)
from app.db.session import get_db
from app.domain.coupon_issuance import coupon_budget_exhausted, lock_coupon_template, try_issue_coupon
from app.domain.coupon_redeem import create_claim_token, decode_redeem_token
from app.models import CouponTemplate, Staff, User, UserCoupon

router = APIRouter(prefix="/admin/v2/manager/coupons", tags=["manager-coupons"])

HALF_PRICE_CODE_PREFIX = "half-price-50-s"
HALF_PRICE_VALIDITY_DAYS = 60
HALF_PRICE_ISSUE_LIMIT = 100


def _half_price_template(db: Session, store_id: int) -> CouponTemplate:
    code = f"{HALF_PRICE_CODE_PREFIX}{store_id}"
    template = lock_coupon_template(db, CouponTemplate.store_id == store_id, CouponTemplate.code == code)
    if template is None:
        template = CouponTemplate(
            store_id=store_id,
            code=code,
            name="半价券（全单5折）",
            coupon_type="percent",
            amount_cents=0,
            percent_off=50,
            min_spend_cents=0,
            validity_days=HALF_PRICE_VALIDITY_DAYS,
            auto_grant_new_user=False,
            is_claimable=False,
            claim_limit=1,
            daily_claimable=False,
            auto_apply=False,
            status="published",
        )
        db.add(template)
        db.flush()
    if template.validity_days != HALF_PRICE_VALIDITY_DAYS:
        template.validity_days = HALF_PRICE_VALIDITY_DAYS
    if template.status != "published":
        raise HTTPException(status_code=409, detail={"code": "COUPON_NOT_PUBLISHED", "message": "半价券未上架"})
    return template


def _issued_count(db: Session, template_id: int) -> int:
    return int(db.scalar(select(sa_func.count()).select_from(UserCoupon).where(
        UserCoupon.template_id == template_id,
    )) or 0)


def _ensure_issue_capacity(db: Session, template: CouponTemplate) -> None:
    if _issued_count(db, template.id) >= HALF_PRICE_ISSUE_LIMIT:
        raise HTTPException(status_code=409, detail={
            "code": "COUPON_SOLD_OUT",
            "message": "半价券 100 张已发完",
        })


class IssueHalfPriceIn(BaseModel):
    user_id: int = Field(gt=0)


@router.post("/half-price/link")
def create_half_price_link(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """生成可发微信的领券链接；顾客登录后领取，最多 100 张。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    template = _half_price_template(db, store_id)
    issued = _issued_count(db, template.id)
    if issued >= HALF_PRICE_ISSUE_LIMIT:
        raise HTTPException(status_code=409, detail={"code": "COUPON_SOLD_OUT", "message": "半价券 100 张已发完"})
    token, expires_at = create_claim_token(store_id, template.id)
    db.commit()
    return {
        "token": token,
        "code": token,
        "expires_at": expires_at.isoformat(),
        "limit": HALF_PRICE_ISSUE_LIMIT,
        "issued": issued,
        "remaining": HALF_PRICE_ISSUE_LIMIT - issued,
        "name": template.name,
        "percent_off": template.percent_off,
    }


class IssueByPhoneIn(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    name: str | None = Field(default=None, max_length=32)


@router.post("/half-price/issue")
def issue_half_price_coupon(
    body: IssueHalfPriceIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """店长给本店顾客发一张无门槛全单5折券（每人最多1张未使用）。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    user = db.scalar(select(User).where(
        User.id == body.user_id,
        User.id.in_(_store_user_ids(store_id)),
    ).with_for_update())
    if not user:
        raise HTTPException(status_code=404, detail={"code": "CUSTOMER_NOT_FOUND", "message": "顾客不属于当前门店"})
    template = _half_price_template(db, store_id)
    _ensure_issue_capacity(db, template)
    unused = db.scalar(select(sa_func.count()).select_from(UserCoupon).where(
        UserCoupon.user_id == user.id,
        UserCoupon.template_id == template.id,
        UserCoupon.status == "unused",
    )) or 0
    if unused >= (template.claim_limit or 1):
        raise HTTPException(status_code=409, detail={
            "code": "COUPON_CLAIM_LIMIT_REACHED",
            "message": "该顾客已有一张未使用的半价券",
        })
    now = datetime.now(UTC)
    coupon = try_issue_coupon(
        db, template, user.id, now + timedelta(days=template.validity_days or HALF_PRICE_VALIDITY_DAYS),
        claimed_at=now,
    )
    if coupon is None:
        raise coupon_budget_exhausted()
    _audit(db, staff, "manager_issue_half_price_coupon", "user_coupon", str(coupon.id), {
        "store_id": store_id,
        "user_id": user.id,
        "template_id": template.id,
        "template_code": template.code,
        "expire_at": coupon.expire_at.isoformat(),
    })
    db.commit()
    return {
        "coupon_id": coupon.id,
        "user_id": user.id,
        "template_id": template.id,
        "name": template.name,
        "percent_off": template.percent_off,
        "expire_at": coupon.expire_at.isoformat(),
        "status": coupon.status,
    }


@router.post("/half-price/issue-by-phone")
def issue_half_price_by_phone(
    body: IssueByPhoneIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """店长给微信好友发券：按手机号找到或创建顾客，不要求有订单。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    phone = body.phone.strip().replace(" ", "")
    if not re.fullmatch(r"1\d{10}", phone):
        raise HTTPException(status_code=422, detail={"code": "PHONE_INVALID", "message": "请输入 11 位手机号"})
    user = db.scalar(select(User).where(User.phone == phone).with_for_update())
    created_customer = False
    if user is None:
        nickname = (body.name or "").strip()[:32] or "微信顾客"
        user = User(
            openid=f"wechat-coupon-{uuid.uuid4().hex}",
            nickname=nickname,
            phone=phone,
            is_member=False,
        )
        db.add(user)
        db.flush()
        created_customer = True
        _audit(db, staff, "manager_create_coupon_customer", "user", str(user.id), {
            "store_id": store_id,
            "phone_masked": _masked_phone(phone),
        })
    template = _half_price_template(db, store_id)
    _ensure_issue_capacity(db, template)
    unused = db.scalar(select(sa_func.count()).select_from(UserCoupon).where(
        UserCoupon.user_id == user.id,
        UserCoupon.template_id == template.id,
        UserCoupon.status == "unused",
    )) or 0
    if unused >= (template.claim_limit or 1):
        raise HTTPException(status_code=409, detail={
            "code": "COUPON_CLAIM_LIMIT_REACHED",
            "message": "该顾客已有一张未使用的半价券",
        })
    now = datetime.now(UTC)
    coupon = try_issue_coupon(
        db, template, user.id, now + timedelta(days=template.validity_days or HALF_PRICE_VALIDITY_DAYS),
        claimed_at=now,
    )
    if coupon is None:
        raise coupon_budget_exhausted()
    _audit(db, staff, "manager_issue_half_price_coupon", "user_coupon", str(coupon.id), {
        "store_id": store_id,
        "user_id": user.id,
        "template_id": template.id,
        "template_code": template.code,
        "expire_at": coupon.expire_at.isoformat(),
        "channel": "wechat_phone",
    })
    db.commit()
    return {
        "coupon_id": coupon.id,
        "user_id": user.id,
        "customer_name": _customer_display_name(user),
        "phone_masked": _masked_phone(phone),
        "created_customer": created_customer,
        "template_id": template.id,
        "name": template.name,
        "percent_off": template.percent_off,
        "expire_at": coupon.expire_at.isoformat(),
        "status": coupon.status,
    }


class CouponTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


class CouponRedeemIn(CouponTokenIn):
    request_id: str = Field(min_length=8, max_length=100)


def _redeemable(db: Session, staff: Staff, token: str):
    payload = decode_redeem_token(token)
    store_id = _resolve_target_store_id(db, staff, None)
    coupon = db.get(UserCoupon, payload["coupon_id"])
    if not coupon or coupon.user_id != payload["user_id"]:
        raise HTTPException(status_code=404, detail={"code": "COUPON_NOT_FOUND", "message": "券不存在"})
    template = db.get(CouponTemplate, coupon.template_id)
    if not template or template.store_id != store_id:
        raise HTTPException(status_code=403, detail={"code": "COUPON_STORE_MISMATCH", "message": "该券不属于当前门店"})
    customer = db.get(User, coupon.user_id)
    if not customer:
        raise HTTPException(status_code=403, detail={"code": "COUPON_CUSTOMER_MISMATCH", "message": "顾客不属于当前门店"})
    if not customer.openid.startswith("guest-coupon-"):
        store_customer = db.scalar(select(User.id).where(
            User.id == coupon.user_id,
            User.id.in_(_store_user_ids(store_id)),
        ))
        if not store_customer:
            raise HTTPException(status_code=403, detail={"code": "COUPON_CUSTOMER_MISMATCH", "message": "顾客不属于当前门店"})
    now = datetime.now(UTC)
    if coupon.status == "used":
        raise HTTPException(status_code=409, detail={"code": "COUPON_ALREADY_USED", "message": "该券已核销"})
    if coupon.status != "unused":
        raise HTTPException(status_code=409, detail={"code": "COUPON_NOT_REDEEMABLE", "message": "该券当前不可核销"})
    if coupon.expire_at and coupon.expire_at.replace(tzinfo=coupon.expire_at.tzinfo or UTC) <= now:
        raise HTTPException(status_code=409, detail={"code": "COUPON_EXPIRED", "message": "该券已过期"})
    return coupon, template, customer, store_id


@router.post("/validate")
def validate_coupon(
    body: CouponTokenIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """扫码预览：只返回脱敏顾客信息与券状态，不写库。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    coupon, template, customer, _ = _redeemable(db, staff, body.token)
    return {
        "valid": True,
        "coupon_id": coupon.id,
        "customer_name": _customer_display_name(customer),
        "phone_masked": _masked_phone(customer.phone),
        "name": template.name,
        "coupon_type": template.coupon_type,
        "percent_off": template.percent_off,
        "amount_cents": template.amount_cents,
        "min_spend_cents": template.min_spend_cents,
        "expire_at": coupon.expire_at.isoformat() if coupon.expire_at else None,
        "status": coupon.status,
    }


@router.post("/redeem")
def redeem_coupon(
    body: CouponRedeemIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """确认核销：原子把 unused 改为 used；重复请求不会二次消费。"""
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    coupon, template, customer, store_id = _redeemable(db, staff, body.token)
    result = db.execute(
        update(UserCoupon)
        .where(UserCoupon.id == coupon.id, UserCoupon.status == "unused")
        .values(status="used")
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "COUPON_ALREADY_USED", "message": "该券已被核销"})
    _audit(db, staff, "manager_redeem_coupon", "user_coupon", str(coupon.id), {
        "store_id": store_id,
        "user_id": coupon.user_id,
        "template_id": template.id,
        "template_code": template.code,
        "request_id": body.request_id,
        "redeemed_at": datetime.now(UTC).isoformat(),
    })
    db.commit()
    return {
        "coupon_id": coupon.id,
        "status": "used",
        "customer_name": _customer_display_name(customer),
        "phone_masked": _masked_phone(customer.phone),
        "name": template.name,
        "redeemed_at": datetime.now(UTC).isoformat(),
    }
