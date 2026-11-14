"""Source consumption history and balance snapshots.

These are independent source records. They never fabricate DIY orders,
recharges, redemptions, wallet or revenue rows, and they never mutate the
existing membership card/entitlement facts. The current ``membership_cards``
row remains the entitlement source; ``membership_balance_snapshots`` is a
display-only observation history and must not change ``card_state``.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MembershipConsumptionBatch(Base):
    __tablename__ = "membership_consumption_batches"
    __table_args__ = (
        UniqueConstraint("source", "store_id", "batch_key", name="uq_member_consumption_batch"),
        CheckConstraint("status IN ('preview', 'applied', 'blocked')", name="ck_member_consumption_batch_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    query_range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    query_range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_page_complete: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    coverage_gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="preview")
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MembershipConsumptionBill(Base):
    __tablename__ = "membership_consumption_bills"
    __table_args__ = (
        UniqueConstraint(
            "source", "store_id", "source_bill_no", "content_sha256",
            name="uq_member_consumption_bill_content",
        ),
        CheckConstraint(
            "bill_type IN ('service', 'open_card', 'package', 'recharge', 'unknown')",
            name="ck_member_consumption_bill_type",
        ),
        CheckConstraint(
            "bill_status IN ('normal_settled', 'voided', 'reversed', 'unknown')",
            name="ck_member_consumption_bill_status",
        ),
        CheckConstraint(
            "attribution_status IN ('owned', 'shared', 'unresolved')",
            name="ck_member_consumption_attribution",
        ),
        CheckConstraint(
            "refund_status IN ('none', 'partial', 'refunded', 'void', 'unknown')",
            name="ck_member_consumption_refund",
        ),
        Index("ix_member_consumption_bill_user_store", "user_id", "store_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("membership_consumption_batches.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    source_bill_no: Mapped[str] = mapped_column(String(128), nullable=False)
    source_bill_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bill_type: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    bill_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    source_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_current_marker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    store_price_total_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settled_total_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_evidence_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price_plan_discount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    coupon_payment_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_principal_debit_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_bonus_debit_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cash_payment_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    other_payment_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("membership_cards.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    attribution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved")
    refund_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    original_bill_id: Mapped[int | None] = mapped_column(
        ForeignKey("membership_consumption_bills.id"), nullable=True
    )
    source_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MembershipConsumptionLine(Base):
    __tablename__ = "membership_consumption_lines"
    __table_args__ = (
        Index("ix_member_consumption_line_bill", "bill_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        ForeignKey("membership_consumption_bills.id"), nullable=False
    )
    source_line_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    store_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settled_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_breakdown_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    line_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class MembershipBalanceSnapshot(Base):
    __tablename__ = "membership_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "card_id", "observed_at", "source_batch_id",
            name="uq_member_balance_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("membership_cards.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    principal_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bonus_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_batch_id: Mapped[int] = mapped_column(
        ForeignKey("membership_consumption_batches.id"), nullable=False
    )
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
