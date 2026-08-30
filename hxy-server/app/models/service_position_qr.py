"""服务位二维码主数据：二维码投放、停用和换绑历史必须可追溯。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ServicePositionQr(Base):
    __tablename__ = "service_position_qrs"
    __table_args__ = (
        Index(
            "uq_service_position_qrs_active_room",
            "room_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="personal_qr")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_position_qrs.id"), nullable=True, index=True
    )
    created_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
