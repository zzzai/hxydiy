"""Persistent operational exceptions that need a human owner and resolution."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OperationalException(Base):
    """A store-scoped exception with a stable dedupe key.

    Reconciliation and other detectors upsert by ``dedupe_key`` so repeated
    scans do not create duplicate work items.
    """

    __tablename__ = "operational_exceptions"
    __table_args__ = (
        UniqueConstraint("store_id", "dedupe_key", name="uq_operational_exceptions_store_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    exception_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(160), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    entity_type: Mapped[str] = mapped_column(String(32), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    resolution_note: Mapped[str] = mapped_column(String(500), default="")
    assigned_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
