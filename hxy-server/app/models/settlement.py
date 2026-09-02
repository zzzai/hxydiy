"""服务减免与退款登记，和订单状态审计分开保存财务调整事实。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SettlementAdjustment(Base):
    __tablename__ = "settlement_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    selection_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("selection_sessions.id"), nullable=True, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(24), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    original_amount_cents: Mapped[int] = mapped_column(Integer)
    final_amount_cents: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    responsibility: Mapped[str] = mapped_column(String(24), default="other", index=True)
    status: Mapped[str] = mapped_column(String(24), default="registered", index=True)
    payment_allocation: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
