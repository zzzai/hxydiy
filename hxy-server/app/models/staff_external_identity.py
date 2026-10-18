from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.session import Base


class StaffExternalIdentity(Base):
    """ORM binding writes atomically revoke provider sessions.

    Bulk/raw binding updates bypass mapper events and are unsupported unless
    the same UPDATE increments binding_version and clears provider_verified_at.
    """

    __tablename__ = "staff_external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "corp_id", "userid", name="uq_staff_external_identity_subject"),
        CheckConstraint("userid = lower(userid)", name="ck_staff_external_identity_userid_canonical"),
        CheckConstraint("binding_version >= 1", name="ck_staff_external_identity_version"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_staff_external_identity_status"),
        Index("uq_staff_external_identity_active_staff", "provider", "staff_id", unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="wecom")
    corp_id: Mapped[str] = mapped_column(String(128))
    userid: Mapped[str] = mapped_column(String(128))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.id"), nullable=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    binding_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    provider_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @validates("userid")
    def canonicalize_userid(self, key, value):
        return value.lower()


@event.listens_for(StaffExternalIdentity, "before_update")
def advance_binding_version(mapper, connection, target):
    state = inspect(target)
    if state.attrs.binding_version.history.has_changes() or any(state.attrs[key].history.has_changes() for key in ("provider", "corp_id", "userid", "staff_id", "technician_id", "store_id", "status")):
        # Evaluate against the database row, never a potentially stale ORM value.
        # SQLAlchemy expires the expression result and refreshes it on access.
        target.binding_version = StaffExternalIdentity.binding_version + 1
        target.provider_verified_at = None


class StaffOAuthAttempt(Base):
    __tablename__ = "staff_oauth_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'used', 'failed')", name="ck_staff_oauth_attempt_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    nonce_hash: Mapped[str] = mapped_column(String(64))
    browser_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    identity_id: Mapped[int | None] = mapped_column(ForeignKey("staff_external_identities.id"), nullable=True)
    binding_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credentials_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
