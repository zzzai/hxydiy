from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LearningCourseVersion(Base):
    __tablename__ = "learning_course_versions"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_learning_course_version"),
        CheckConstraint("status IN ('pilot', 'published', 'retired')", name="ck_learning_course_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(48))
    version: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="pilot")
    content: Mapped[dict] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    approval_reference: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffLearningAssignment(Base):
    __tablename__ = "staff_learning_assignments"
    __table_args__ = (
        UniqueConstraint("store_id", "staff_id", "course_version_id", name="uq_staff_learning_assignment"),
        CheckConstraint("revision >= 0", name="ck_staff_learning_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    staff_name: Mapped[str] = mapped_column(String(32))
    course_version_id: Mapped[str] = mapped_column(ForeignKey("learning_course_versions.id"))
    assigned_by: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sections_read: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class StaffLearningEvent(Base):
    __tablename__ = "staff_learning_events"
    __table_args__ = (
        UniqueConstraint("store_id", "actor_id", "request_id", name="uq_staff_learning_request"),
        CheckConstraint("kind IN ('assign', 'mark_section', 'submit', 'follow_up')", name="ck_staff_learning_event_kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("staff_learning_assignments.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    actor_name: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(100))
    assignment_revision: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
