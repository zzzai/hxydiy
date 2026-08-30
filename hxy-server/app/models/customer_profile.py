from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    selection_session_id: Mapped[str | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.id"), nullable=True, index=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="service_observation", server_default="service_observation")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    correction_of_id: Mapped[int | None] = mapped_column(ForeignKey("customer_profile_records.id"), nullable=True, index=True)
    correction_reason: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
