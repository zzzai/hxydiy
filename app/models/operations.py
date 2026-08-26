# 运营模块：房间/床位/沙发、技师管理

from datetime import datetime

from sqlalchemy import Boolean, JSON, DateTime, ForeignKey, Integer, String, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Room(Base):
    """空间容器与实际服务位。

    房间是空间容器时 is_space_container=True，不参与占用和服务流转；
    沙发、床位等实际服务位通过 parent_room_id 关联到房间（沙发可为空）。
    """

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    parent_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))             # 如 "1 号包间""靠窗沙发 A"
    room_type: Mapped[str] = mapped_column(String(16), default="room")  # room / sofa / bed
    floor: Mapped[str] = mapped_column(String(16), default="")          # 楼层
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    room_group: Mapped[str] = mapped_column(String(16), default="sofa")
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    current_tech: Mapped[str] = mapped_column(String(64), default="")           # 最大容纳人数
    status: Mapped[str] = mapped_column(String(16), default="available", index=True)
    # available / occupied / cleaning / maintenance
    note: Mapped[str] = mapped_column(String(256), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    customer_label: Mapped[str] = mapped_column(String(64), default="")
    map_x: Mapped[float] = mapped_column(Float, default=0.0)
    map_y: Mapped[float] = mapped_column(Float, default=0.0)
    map_width: Mapped[float] = mapped_column(Float, default=0.2)
    map_height: Mapped[float] = mapped_column(Float, default=0.13)
    customer_selectable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_space_container: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_service_position: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    operational_status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Technician(Base):
    """技师 / 调理师——排班 + 提成"""

    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(32))
    phone: Mapped[str] = mapped_column(String(20), default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    gender: Mapped[str] = mapped_column(String(8), default="")
    level: Mapped[str] = mapped_column(String(16), default="初级")  # 初级 / 中级 / 高级 / 督导
    # skills: 可服务的项目 ID 列表，如 [1, 3, 5]
    skills: Mapped[list] = mapped_column(JSON, default=list)
    intro: Mapped[str] = mapped_column(String(256), default="")
    # commission: {"bath": 600, "balance_base": 1200, "balance_override": {"7": 1500}}（分）
    commission_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    default_commission_rate: Mapped[float] = mapped_column(Float, default=0.3)  # 默认提成比例
    hire_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="available", index=True)
    # available / busy / off / resigned
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    staff_account = relationship("Staff", back_populates="technician", uselist=False, foreign_keys="Staff.technician_id")
