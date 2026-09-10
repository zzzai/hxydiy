"""会员权益发放与核销记录。"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MembershipBenefitGrant(Base):
    __tablename__ = "membership_benefit_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "membership_cycle_id",
            name="uq_membership_benefit_cycle",
        ),
        UniqueConstraint("used_service_line_id", name="uq_membership_benefit_used_service_line"),
        CheckConstraint(
            "status IN ('available', 'used', 'voided')",
            name="ck_membership_benefit_status",
        ),
        Index("ix_membership_benefit_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    benefit_type: Mapped[str] = mapped_column(String(32), default="annual_project_gift")
    membership_cycle_id: Mapped[str] = mapped_column(String(64))
    membership_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    membership_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    cycle_state: Mapped[str] = mapped_column(String(16), default="active", index=True)
    payment_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 非现金渠道仅保存脱敏尾号；人工收据号可作为门店线下凭据保存。
    payment_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    refund_disposition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recovery_idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="available", index=True)
    used_service_line_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_lines.id"), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
