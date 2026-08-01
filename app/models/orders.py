# 交易模块：订单、订单事件（状态机审计）、购物车

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# 订单状态机（服务端唯一权威，前端只能请求动作）
# draft -> pending_payment -> paid -> confirmed -> checked_in -> in_service -> completed
# 异常分支：
#   pending_payment -> expired / cancelled
#   paid / confirmed -> cancellation_requested -> cancelled / refund_pending
#   paid / confirmed / completed -> refund_pending -> partially_refunded / refunded / refund_rejected

ORDER_STATUSES = {
    "draft", "pending_payment", "paid", "confirmed", "checked_in", "in_service",
    "completed", "expired", "cancelled", "cancellation_requested",
    "refund_pending", "refunded", "refund_rejected", "partially_refunded",
}

PAY_STATUSES = {"unpaid", "paid", "refunded"}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    order_type: Mapped[str] = mapped_column(String(16))  # service / product / member
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    booking_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 2026-08-30
    booking_time: Mapped[str | None] = mapped_column(String(5), nullable=True)   # 14:00（1 小时粒度）
    coupon_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    member_discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    pay_amount_cents: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    pay_status: Mapped[str] = mapped_column(String(16), default="unpaid", index=True)
    pay_transaction_id: Mapped[str] = mapped_column(String(64), default="")
    refund_status: Mapped[str] = mapped_column(String(16), default="")

    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderEvent(Base):
    """订单状态流转审计：每次转换记录原状态/新状态/动作/操作者/原因/幂等键。"""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(24), default="")
    to_status: Mapped[str] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(32))  # create / pay / confirm / cancel / refund...
    operator: Mapped[str] = mapped_column(String(64), default="system")
    reason: Mapped[str] = mapped_column(String(256), default="")
    idempotency_key: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
