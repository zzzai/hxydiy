from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerProfileConsent(Base):
    __tablename__ = "customer_profile_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(256))
    data_categories_json: Mapped[list] = mapped_column(JSON, default=list)
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_method: Mapped[str] = mapped_column(String(32))
    consent_text_version: Mapped[str] = mapped_column(String(64))
    selection_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("selection_sessions.id"), nullable=True, index=True,
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)


class CustomerProfileCurrent(Base):
    __tablename__ = "customer_profile_current"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "profile_code", "profile_value_key", "body_area_code", "body_side",
            name="uq_customer_profile_current_dimension",
        ),
        Index("ix_customer_profile_current_customer_valid", "customer_id", "status", "valid_until"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    profile_code: Mapped[str] = mapped_column(String(64))
    profile_value_key: Mapped[str] = mapped_column(String(128), default="")
    profile_value_json: Mapped[dict] = mapped_column(JSON)
    body_area_code: Mapped[str] = mapped_column(String(64), default="")
    body_side: Mapped[str] = mapped_column(String(16), default="")
    source_record_id: Mapped[int] = mapped_column(ForeignKey("customer_profile_records.id"), index=True)
    first_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmation_count: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sensitivity_level: Mapped[str] = mapped_column(String(16), default="normal")
    consent_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_profile_consents.id"), nullable=True,
    )
    taxonomy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
