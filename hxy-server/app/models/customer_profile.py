from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerProfileRecord(Base):
    """服务完成后的顾客画像快记；内容是服务参考，不构成医疗判断。"""

    __tablename__ = "customer_profile_records"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "created_by_staff_id",
            "idempotency_key",
            name="uq_customer_profile_records_creator_idempotency",
        ),
        Index(
            "ix_customer_profile_store_user_confirmed_created",
            "store_id", "user_id", "customer_confirmed", text("created_at DESC"),
        ),
        Index(
            "ix_customer_profile_store_technician_created",
            "store_id", "technician_id", text("created_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    selection_session_id: Mapped[str | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.id"), nullable=True, index=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="service_observation", server_default="service_observation")
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    taxonomy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    correction_of_id: Mapped[int | None] = mapped_column(ForeignKey("customer_profile_records.id"), nullable=True, index=True)
    correction_reason: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
