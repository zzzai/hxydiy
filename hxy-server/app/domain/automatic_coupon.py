"""线下结算普通券的只读预选与原子核销。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CouponTemplate, UserCoupon


@dataclass(frozen=True)
class AutomaticCouponResult:
    coupon_id: int | None
    coupon_name: str | None
    template_id: int | None
    coupon_type: str | None
    raw_discount_cents: int
    discount_cents: int
    payable_after_coupon_cents: int
    member_floor_cents: int
    expire_at: str | None

    def as_dict(self) -> dict:
        return {
            "coupon_id": self.coupon_id,
            "coupon_name": self.coupon_name,
            "template_id": self.template_id,
            "coupon_type": self.coupon_type,
            "raw_discount_cents": self.raw_discount_cents,
            "discount_cents": self.discount_cents,
            "payable_after_coupon_cents": self.payable_after_coupon_cents,
            "member_floor_cents": self.member_floor_cents,
            "expire_at": self.expire_at,
        }

    def audit_item(self) -> dict:
        return {"item_kind": "automatic_coupon", **self.as_dict()}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _empty_result(current_payable_cents: int, member_floor_cents: int) -> AutomaticCouponResult:
    return AutomaticCouponResult(
        coupon_id=None,
        coupon_name=None,
        template_id=None,
        coupon_type=None,
        raw_discount_cents=0,
        discount_cents=0,
        payable_after_coupon_cents=current_payable_cents,
        member_floor_cents=member_floor_cents,
        expire_at=None,
    )


def select_automatic_coupon(
    db: Session,
    *,
    customer_id: int | None,
    pricing: dict,
    now: datetime | None = None,
    lock: bool = False,
) -> AutomaticCouponResult:
    """按实际优惠、到期时间和领券 ID 确定最多一张普通券。"""
    current_payable = max(0, int(pricing.get("payable_total_cents", 0) or 0))
    member_floor = max(
        0,
        int(pricing.get("member_total_cents", current_payable) or 0),
    )
    available_discount = max(0, current_payable - member_floor)
    empty = _empty_result(current_payable, member_floor)
    if customer_id is None or available_discount == 0:
        return empty

    settled_at = _utc(now or datetime.now(UTC))
    statement = (
        select(UserCoupon, CouponTemplate)
        .join(CouponTemplate, CouponTemplate.id == UserCoupon.template_id)
        .where(
            UserCoupon.user_id == customer_id,
            UserCoupon.status == "unused",
        )
        .order_by(UserCoupon.id.asc())
    )
    if lock:
        statement = statement.with_for_update(of=UserCoupon)

    candidates: list[tuple[tuple, AutomaticCouponResult]] = []
    for user_coupon, template in db.execute(statement):
        expires_at = _utc(user_coupon.expire_at) if user_coupon.expire_at else None
        if expires_at is not None and expires_at <= settled_at:
            continue
        if current_payable < max(0, int(template.min_spend_cents or 0)):
            continue
        if template.coupon_type == "percent":
            raw_discount = current_payable * max(0, int(template.percent_off or 0)) // 100
        else:
            raw_discount = max(0, int(template.amount_cents or 0))
        actual_discount = min(available_discount, raw_discount)
        if actual_discount <= 0:
            continue
        result = AutomaticCouponResult(
            coupon_id=user_coupon.id,
            coupon_name=template.name,
            template_id=template.id,
            coupon_type=template.coupon_type,
            raw_discount_cents=raw_discount,
            discount_cents=actual_discount,
            payable_after_coupon_cents=current_payable - actual_discount,
            member_floor_cents=member_floor,
            expire_at=expires_at.isoformat() if expires_at else None,
        )
        candidates.append((
            (
                -actual_discount,
                expires_at is None,
                expires_at.timestamp() if expires_at else float("inf"),
                user_coupon.id,
            ),
            result,
        ))

    if not candidates:
        return empty
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[0][1]


def mark_automatic_coupon_used(
    db: Session,
    selection: AutomaticCouponResult,
    *,
    order_id: int,
) -> None:
    if selection.coupon_id is None:
        return
    coupon = db.get(UserCoupon, selection.coupon_id)
    if coupon is None or coupon.status != "unused":
        raise RuntimeError("automatic coupon is no longer unused")
    coupon.status = "used"
    coupon.used_order_id = order_id
