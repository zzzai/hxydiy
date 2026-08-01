# 营销与会员模块：券定义、用户券、会员计划、储值记录

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CouponTemplate(Base):
    """券定义（后台配置）：新客自动发券等。"""

    __tablename__ = "coupon_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    # fixed 满减券（amount_cents 为面额）；discount 折扣券（percent_off 为折扣率）
    coupon_type: Mapped[str] = mapped_column(String(16), default="fixed")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    percent_off: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    auto_grant_new_user: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft/published/archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserCoupon(Base):
    __tablename__ = "user_coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("coupon_templates.id"))
    # unused -> locked(下单锁定) -> used / expired
    status: Mapped[str] = mapped_column(String(16), default="unused", index=True)
    used_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemberPlan(Base):
    """会员计划：annual 年度权益卡 / stored 储值 / monthly 泡脚月卡。"""

    __tablename__ = "member_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column(Integer)
    benefits: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recharge(Base):
    """储值流水（分）。退款须到店线下办理，系统记录线下退款登记。"""

    __tablename__ = "recharges"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    gift_cents: Mapped[int] = mapped_column(Integer, default=0)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending / success / offline_refund_registered
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
