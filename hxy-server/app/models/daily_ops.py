"""店长每日经营、区域照片、晨会录音和总部抽检记录。"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
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
    checklist_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
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
        UniqueConstraint("checkin_id", "area", "slot", name="uq_daily_area_photo_slot"),
        CheckConstraint("slot BETWEEN 1 AND 3", name="ck_daily_area_photo_slot"),
        CheckConstraint(
            "area IN ('restroom', 'water_room', 'cashier', 'rest_area', 'foot_area', 'herbal_prep')",
            name="ck_daily_area_photo_area",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("daily_store_checkins.id"), index=True)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    area: Mapped[str] = mapped_column(String(24))
    media_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"))
    note: Mapped[str] = mapped_column(String(300), default="")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyAreaPhotoReview(Base):
    __tablename__ = "daily_area_photo_reviews"
    __table_args__ = (
        UniqueConstraint("photo_id", "media_id", name="uq_inspection_review_photo_media"),
        CheckConstraint("state IN ('pending','running','done','failed','superseded')", name="ck_inspection_review_state"),
        CheckConstraint("manual_verdict IN ('pass','fix','retake')", name="ck_inspection_review_manual"),
        Index("ix_inspection_review_queue", "state", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("daily_area_photos.id", ondelete="CASCADE"))
    media_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(64))
    rubric: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_verdict: Mapped[str | None] = mapped_column(String(12))
    manual_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    manual_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
