from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerTagContribution(Base):
    __tablename__ = "customer_tag_contributions"
    __table_args__ = (
        UniqueConstraint("store_id", "created_by_staff_id", "idempotency_key", name="uq_customer_tag_contribution_creator_key"),
        Index("uq_customer_tag_contribution_active_context", "user_id", "tag_id", "created_by_staff_id", "occupancy_id", unique=True, postgresql_where=text("revoked_at IS NULL"), sqlite_where=text("revoked_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("customer_tags.id"), index=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    occupancy_id: Mapped[int] = mapped_column(ForeignKey("position_occupancies.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(256), default="", server_default="")
