"""店长每日经营、区域照片、晨会录音和总部抽检记录。"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DailyStoreCheckin(Base):
    __tablename__ = "daily_store_checkins"
    __table_args__ = (
        UniqueConstraint("store_id", "business_date", name="uq_daily_store_checkin_date"),
        CheckConstraint("status IN ('draft', 'submitted')", name="ck_daily_store_checkin_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    manager_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyAreaPhoto(Base):
    __tablename__ = "daily_area_photos"
    __table_args__ = (
        UniqueConstraint("checkin_id", "area", name="uq_daily_area_photo_area"),
        CheckConstraint(
            "area IN ('restroom', 'water_room', 'cashier', 'rest_area', 'foot_area')",
            name="ck_daily_area_photo_area",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("daily_store_checkins.id"), index=True)
    area: Mapped[str] = mapped_column(String(24))
    media_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"))
    note: Mapped[str] = mapped_column(String(300), default="")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyMeetingRecording(Base):
    __tablename__ = "daily_meeting_recordings"
    __table_args__ = (
        CheckConstraint(
            "transcript_status IN ('uploaded', 'transcribing', 'transcribed', 'failed', 'not_configured')",
            name="ck_daily_meeting_transcript_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("daily_store_checkins.id"), index=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"))
    title: Mapped[str] = mapped_column(String(80), default="晨会")
    attendees: Mapped[str] = mapped_column(String(300), default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    transcript_status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    transcript_text: Mapped[str] = mapped_column(Text, default="")
    summary_text: Mapped[str] = mapped_column(Text, default="")
    asr_provider: Mapped[str] = mapped_column(String(24), default="")
    asr_task_id: Mapped[str] = mapped_column(String(128), default="")
    error_message: Mapped[str] = mapped_column(String(500), default="")
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingAssessment(Base):
    __tablename__ = "training_assessments"
    __table_args__ = (
        CheckConstraint("kind IN ('theory', 'practical')", name="ck_training_assessment_kind"),
        CheckConstraint("result IN ('pending', 'passed', 'failed')", name="ck_training_assessment_result"),
        CheckConstraint(
            "hq_status IN ('pending', 'passed', 'returned')",
            name="ck_training_assessment_hq_status",
        ),
        Index("ix_training_assessments_store_staff", "store_id", "staff_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_learning_assignments.id"), nullable=True, index=True
    )
    course_name: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(16), default="practical")
    result: Mapped[str] = mapped_column(String(16), default="pending")
    manager_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    manager_note: Mapped[str] = mapped_column(String(500), default="")
    manager_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hq_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    hq_reviewer_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    hq_note: Mapped[str] = mapped_column(String(500), default="")
    hq_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
