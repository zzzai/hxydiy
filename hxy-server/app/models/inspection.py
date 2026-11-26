"""Links between inspection evidence and durable WeCom delivery receipts."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InspectionFollowup(Base):
    __tablename__ = "inspection_followups"
    __table_args__ = (
        UniqueConstraint("root_id", "sequence", name="uq_inspection_followup_sequence"),
        CheckConstraint("sequence > 0 AND root_id <> review_id", name="ck_inspection_followup_sequence"),
    )

    review_id: Mapped[int] = mapped_column(ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"), primary_key=True, autoincrement=False)
    root_id: Mapped[int] = mapped_column(ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InspectionDelivery(Base):
    __tablename__ = "inspection_deliveries"
    __table_args__ = (
        UniqueConstraint("event_key", "binding_id", name="uq_inspection_delivery_recipient"),
        CheckConstraint("state IN ('pending','sending','accepted','rejected','unknown','cancelled')",
                        name="ck_inspection_delivery_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(80))
    binding_id: Mapped[int] = mapped_column(ForeignKey("staff_external_identities.id", ondelete="CASCADE"))
    binding_version: Mapped[int] = mapped_column(Integer)
    root_id: Mapped[int | None] = mapped_column(ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"))
    review_id: Mapped[int | None] = mapped_column(ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"))
    week_start: Mapped[date | None] = mapped_column(Date)
    summary_text: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
