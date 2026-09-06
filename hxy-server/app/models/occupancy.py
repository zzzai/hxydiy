"""服务位动态占用：与房位静态配置、支付订单和项目倒计时分离。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


OCCUPANCY_ACTIVE_STATUSES = {
    "held",
    "waiting_service",
    "in_service",
    "post_service_present",
    "cleaning",
}


class PositionOccupancy(Base):
    __tablename__ = "position_occupancies"
    __table_args__ = (
        Index(
            "ix_position_occupancies_store_technician_finished",
            "store_id",
            "serviced_by_technician_id",
            "actual_service_end_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    serviced_by_technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id"), nullable=True, index=True
    )

    # 活动期间等于真实外键；释放后置空。可空唯一键可同时兼容 SQLite 和 PostgreSQL，
    # 并在数据库层阻止同一服务位或同一选单出现两个活动占用。
    active_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id"), nullable=True, unique=True, index=True
    )
    active_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("selection_sessions.id"), nullable=True, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="held", index=True)
    source: Mapped[str] = mapped_column(String(16), default="personal_qr")
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    retained_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    expected_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_service_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str] = mapped_column(String(256), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
