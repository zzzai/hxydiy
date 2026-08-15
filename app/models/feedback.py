from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ServiceFeedback(Base):
    __tablename__ = "service_feedback"
    __table_args__ = (UniqueConstraint("selection_session_id", name="uq_service_feedback_session"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    rating: Mapped[int] = mapped_column()
    tags: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
