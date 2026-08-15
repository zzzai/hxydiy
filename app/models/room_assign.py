# 运营模块补充：房间-技师-项目排钟关联

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RoomAssignment(Base):
    """房间排钟：绑定技师 + 可服务项目 + 提成规则
    
    一个房间可以绑定多个技师和多个项目。技师在该房间内可服务的项目和提成。
    """

    __tablename__ = "room_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)
    # 指定技师在此房间可服务的项目（空列表 = 全部）
    project_ids: Mapped[list] = mapped_column(JSON, default=list)
    # 各项目提成覆盖（可选，覆盖技师默认提成），格式: {"project_id": commission_cents}
    commission_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
