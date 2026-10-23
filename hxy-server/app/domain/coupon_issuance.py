"""Shared issuance transaction boundary for coupon template budgets."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CouponTemplate, UserCoupon


def lock_coupon_template(db: Session, *criteria) -> CouponTemplate | None:
    # Refresh cached attributes after waiting for a concurrent template update.
    return db.scalar(
        select(CouponTemplate).where(*criteria).with_for_update()
        .execution_options(populate_existing=True)
    )


def coupon_budget_exhausted() -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "COUPON_BUDGET_EXHAUSTED",
        "message": "券预算不足，不能继续发放",
    })


def try_issue_coupon(
    db: Session, template: CouponTemplate, user_id: int, expire_at: datetime,
    *, claimed_at: datetime | None = None,
) -> UserCoupon | None:
    """Caller holds the template lock until its outer transaction completes."""
    if template.budget_cents is not None and template.coupon_type == "fixed":
        issued_total = int(db.scalar(
            select(func.count()).select_from(UserCoupon)
            .where(UserCoupon.template_id == template.id)
        ) or 0)
        if template.amount_cents * (issued_total + 1) > template.budget_cents:
            return None
    values = {"claimed_at": claimed_at} if claimed_at is not None else {}
    coupon = UserCoupon(
        user_id=user_id, template_id=template.id, status="unused",
        expire_at=expire_at, **values,
    )
    db.add(coupon)
    # Callers disable autoflush; subsequent issuance in this transaction must see it.
    db.flush()
    return coupon


def require_issued_value_unchanged(db: Session, template: CouponTemplate, changes: dict) -> None:
    budgeted = template.budget_cents is not None or changes.get("budget_cents") is not None
    changed_value = any(
        key in changes and changes[key] != getattr(template, key)
        for key in ("amount_cents", "coupon_type")
    )
    if budgeted and changed_value and db.scalar(
        select(UserCoupon.id).where(UserCoupon.template_id == template.id).limit(1)
    ) is not None:
        raise HTTPException(status_code=409, detail={
            "code": "COUPON_ISSUED_VALUE_IMMUTABLE",
            "message": "已发放的预算券不能修改面额或券类型",
        })
