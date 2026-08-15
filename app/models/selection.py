"""到店选项目会话：独立于订单的顾客服务需求草稿。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


SELECTION_STATUSES = {"draft", "submitted", "confirmed", "cancelled", "expired"}
REVISION_STATES = {"submitted", "awaiting_staff_confirmation", "confirmed", "rejected", "superseded"}
CHANGE_REQUEST_STATES = {"awaiting_staff_confirmation", "approved", "rejected", "cancelled"}
SERVICE_LINE_STATES = {"pending", "in_service", "completed", "cancelled"}


class SelectionSession(Base):
    __tablename__ = "selection_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    access_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # 线下前台接待后生成的服务订单，防止同一份 DIY 选单重复转单。
    fulfillment_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, unique=True, index=True
    )
    source: Mapped[str] = mapped_column(String(16), default="in_store")
    device_label: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    diy_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    pricing_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    store_total_cents: Mapped[int] = mapped_column(Integer, default=0)
    member_total_cents: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SelectionRevision(Base):
    """顾客每次提交的不可变选单与报价快照。"""

    __tablename__ = "selection_revisions"
    __table_args__ = (
        UniqueConstraint("selection_session_id", "revision_no", name="uq_selection_revision_no"),
        UniqueConstraint("selection_session_id", "idempotency_key", name="uq_selection_revision_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(96))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class SelectionChangeRequest(Base):
    """服务中顾客新增项目，必须由前台确认后才能进入执行项。"""

    __tablename__ = "selection_change_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    selection_revision_id: Mapped[str] = mapped_column(ForeignKey("selection_revisions.id"), index=True)
    state: Mapped[str] = mapped_column(String(32), default="awaiting_staff_confirmation", index=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class ServiceLine(Base):
    """前台确认后的实际执行项目；不随顾客后续选单变化。"""

    __tablename__ = "service_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    selection_session_id: Mapped[str] = mapped_column(ForeignKey("selection_sessions.id"), index=True)
    selection_revision_id: Mapped[str] = mapped_column(ForeignKey("selection_revisions.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
