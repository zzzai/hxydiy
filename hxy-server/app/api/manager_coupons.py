"""Manager-issued half-price coupons and one-time scan redemption.

This is a standalone marketing redemption: it marks the coupon used and does
not mutate an order or payment. The customer QR is a short-lived signed token;
the manager endpoint re-checks the coupon, store and customer on every call.
"""

from datetime import UTC, datetime, timedelta
import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, StrictBool
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
from app.domain.coupon_redeem import create_claim_token, create_poster_token, decode_redeem_token
from app.models import AuditLog, CouponPosterLink, CouponTemplate, Staff, Store, User, UserCoupon

router = APIRouter(prefix="/admin/v2/manager/coupons", tags=["manager-coupons"])

HALF_PRICE_CODE_PREFIX = "half-price-50-s"
HALF_PRICE_VALIDITY_DAYS = 60
HALF_PRICE_ISSUE_LIMIT = 100


def _half_price_template(db: Session, store_id: int, *, preserve_existing: bool = False) -> CouponTemplate:
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
    if preserve_existing and (
        template.validity_days != HALF_PRICE_VALIDITY_DAYS
        or template.coupon_type != "percent" or template.percent_off != 50
        or template.min_spend_cents != 0
    ):
        raise HTTPException(status_code=409, detail={
            "code": "COUPON_CONFIG_MISMATCH", "message": "活动设置与半价券海报不一致，请先核对活动配置",
        })
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


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _history_status(coupon: UserCoupon, now: datetime) -> str:
    if coupon.status == "used":
        return "used"
    expire_at = _aware(coupon.expire_at)
    if expire_at and expire_at <= now:
        return "expired"
    return "unused"


@router.get("/history")
def coupon_history(
    days: int = 30,
    kind: str = "all",
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """本店半价券的发券、领取、核销记录。

    发券以 UserCoupon 的实际创建为准；仅生成链接不算发券。
    领取和直接发券都来自 UserCoupon，核销时间来自 AuditLog。
    """
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    days = max(1, min(int(days or 30), 90))
    limit = max(1, min(int(limit or 30), 100))
    offset = max(0, int(offset or 0))
    if kind not in {"all", "issued", "redeemed"}:
        kind = "all"

    template = db.scalar(select(CouponTemplate).where(
        CouponTemplate.store_id == store_id,
        CouponTemplate.code == f"{HALF_PRICE_CODE_PREFIX}{store_id}",
    ))
    now = datetime.now(UTC)
    if template is None:
        return {
            "summary": {"issued": 0, "redeemed": 0, "unused": 0, "expired": 0},
            "items": [],
            "next_offset": None,
        }

    start = now - timedelta(days=days)
    issued_rows = list(db.execute(
        select(UserCoupon, User)
        .join(User, User.id == UserCoupon.user_id)
        .where(
            UserCoupon.template_id == template.id,
            UserCoupon.claimed_at >= start,
        )
        .order_by(UserCoupon.claimed_at.desc())
    ).all())
    redeem_rows = list(db.scalars(select(AuditLog).where(
        AuditLog.action == "manager_redeem_coupon",
        AuditLog.store_id == store_id,
        AuditLog.entity_id.in_([str(coupon.id) for coupon, _ in issued_rows]) if issued_rows else False,
        AuditLog.created_at >= start,
    ).order_by(AuditLog.created_at.desc())))

    coupon_ids = {coupon.id for coupon, _ in issued_rows}
    coupon_ids.update(int(row.entity_id) for row in redeem_rows if row.entity_id.isdigit())
    coupons = {coupon.id: coupon for coupon, _ in issued_rows}
    customers = {coupon.id: user for coupon, user in issued_rows}
    missing = [coupon_id for coupon_id in coupon_ids if coupon_id not in coupons]
    if missing:
        for coupon in db.scalars(select(UserCoupon).where(UserCoupon.id.in_(missing))):
            coupons[coupon.id] = coupon
            customer = db.get(User, coupon.user_id)
            if customer:
                customers[coupon.id] = customer

    direct_ids = {
        int(row.entity_id)
        for row in db.scalars(select(AuditLog).where(
            AuditLog.action == "manager_issue_half_price_coupon",
            AuditLog.entity_type == "user_coupon",
            AuditLog.entity_id.in_([str(coupon_id) for coupon_id in coupon_ids]),
        )) if row.entity_id.isdigit()
    }
    actor_ids = {int(row.actor_id) for row in redeem_rows if row.actor_id.isdigit()}
    actor_names = {
        staff_id: name
        for staff_id, name in db.execute(select(Staff.id, Staff.name).where(Staff.id.in_(actor_ids))).all()
    } if actor_ids else {}

    events = []
    for coupon, user in issued_rows:
        status = _history_status(coupon, now)
        at = _aware(coupon.claimed_at) or now
        events.append({
            "id": f"issue:{coupon.id}",
            "kind": "issued",
            "at": at.isoformat(),
            "coupon_id": coupon.id,
            "customer_name": _customer_display_name(user),
            "phone_masked": _masked_phone(user.phone) if user.phone else "—",
            "status": status,
            "source": "direct" if coupon.id in direct_ids else "link",
            "actor_name": None,
            "template_name": template.name,
        })
    for row in redeem_rows:
        coupon_id = int(row.entity_id) if row.entity_id.isdigit() else 0
        coupon = coupons.get(coupon_id)
        user = customers.get(coupon_id)
        if coupon is None or user is None:
            continue
        at = _aware(row.created_at) or now
        events.append({
            "id": f"redeem:{row.id}",
            "kind": "redeemed",
            "at": at.isoformat(),
            "coupon_id": coupon.id,
            "customer_name": _customer_display_name(user),
            "phone_masked": _masked_phone(user.phone) if user.phone else "—",
            "status": "used",
            "source": "direct" if coupon.id in direct_ids else "link",
            "actor_name": actor_names.get(int(row.actor_id)) if row.actor_id.isdigit() else None,
            "template_name": template.name,
        })

    events.sort(key=lambda item: item["at"], reverse=True)
    if kind != "all":
        events = [item for item in events if item["kind"] == kind]

    issued_total = len(issued_rows)
    redeemed_total = sum(1 for coupon, _ in issued_rows if _history_status(coupon, now) == "used")
    unused_total = sum(1 for coupon, _ in issued_rows if _history_status(coupon, now) == "unused")
    expired_total = sum(1 for coupon, _ in issued_rows if _history_status(coupon, now) == "expired")
    page = events[offset:offset + limit]
    return {
        "summary": {
            "issued": issued_total,
            "redeemed": redeemed_total,
            "unused": unused_total,
            "expired": expired_total,
        },
        "items": page,
        "next_offset": offset + limit if offset + limit < len(events) else None,
    }


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


class PosterLinkIn(BaseModel):
    request_id: uuid.UUID


@router.post("/half-price/poster-link")
def create_half_price_poster_link(
    body: PosterLinkIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    # Serialize duplicate creation and first-template creation without touching coupons.
    db.scalar(select(Store.id).where(Store.id == store_id).with_for_update(key_share=True))
    poster = db.scalar(select(CouponPosterLink).where(
        CouponPosterLink.created_by_staff_id == staff.id,
        CouponPosterLink.request_id == str(body.request_id),
    ))
    if poster and poster.store_id != store_id:
        raise HTTPException(status_code=409, detail={"code": "POSTER_REQUEST_CONFLICT", "message": "请求已用于其他门店"})
    template = _half_price_template(db, store_id, preserve_existing=True)
    if poster is None:
        _ensure_issue_capacity(db, template)
        poster = CouponPosterLink(
            store_id=store_id, template_id=template.id, created_by_staff_id=staff.id,
            request_id=str(body.request_id), expires_at=datetime.now(UTC) + timedelta(days=60),
        )
        db.add(poster)
        db.flush()
        _audit(db, staff, "manager_create_coupon_poster", "coupon_poster_link", str(poster.id), {
            "store_id": store_id, "template_id": template.id, "request_id": str(body.request_id),
        })
    token = create_poster_token(poster.id, poster.store_id, _aware(poster.expires_at))
    issued = _issued_count(db, template.id)
    db.commit()
    return {
        "code": token, "poster_id": poster.id, "claimed": poster.coupon_id is not None,
        "expires_at": _aware(poster.expires_at).isoformat(), "limit": HALF_PRICE_ISSUE_LIMIT,
        "issued": issued, "remaining": max(0, HALF_PRICE_ISSUE_LIMIT - issued),
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
    holder_present: StrictBool = False
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
    # A newly registered poster recipient may have no order or membership yet.
    # The store-scoped poster establishes access to this coupon only.
    poster_owner = db.scalar(select(CouponPosterLink.id).where(
        CouponPosterLink.coupon_id == coupon.id,
        CouponPosterLink.store_id == store_id,
        CouponPosterLink.template_id == template.id,
    ))
    if not customer.openid.startswith("guest-coupon-") and poster_owner is None:
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
        "requires_holder_confirmation": db.scalar(select(CouponPosterLink.id).where(
            CouponPosterLink.coupon_id == coupon.id,
        )) is not None,
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
    is_poster = db.scalar(select(CouponPosterLink.id).where(CouponPosterLink.coupon_id == coupon.id)) is not None
    if is_poster and not body.holder_present:
        raise HTTPException(status_code=422, detail={
            "code": "COUPON_HOLDER_CONFIRMATION_REQUIRED",
            "message": "请先核对顾客本人现场出示的券码及账户信息",
        })
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
        "holder_present": body.holder_present,
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
