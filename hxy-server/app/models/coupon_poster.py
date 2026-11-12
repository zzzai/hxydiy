"""Single-claim poster links, separate from reusable campaign links."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CouponPosterLink(Base):
    __tablename__ = "coupon_poster_links"
    __table_args__ = (
        UniqueConstraint("created_by_staff_id", "request_id", name="uq_coupon_poster_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("coupon_templates.id"))
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("user_coupons.id"), nullable=True, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
