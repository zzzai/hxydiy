from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerTrustedDevice(Base):
    __tablename__ = "customer_trusted_devices"
    __table_args__ = (Index("uq_customer_active_trusted_device", "user_id", unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MembershipCode(Base):
    __tablename__ = "membership_codes"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_membership_code_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trusted_device_id: Mapped[int] = mapped_column(ForeignKey("customer_trusted_devices.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="issued", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scanned_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    selection_session_id: Mapped[str | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
