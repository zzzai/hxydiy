from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


STAFF_SCOPE_ROLES = ("brand_admin", "hq_operator", "store_manager", "store_staff")
STAFF_SCOPE_TYPES = ("brand", "store")
STAFF_SCOPE_STATUSES = ("active", "disabled")


class StaffScopeAssignment(Base):
    __tablename__ = "staff_scope_assignments"
    __table_args__ = (
        CheckConstraint(
            "role IN ('brand_admin', 'hq_operator', 'store_manager', 'store_staff')",
            name="ck_staff_scope_assignment_role",
        ),
        CheckConstraint(
            "scope_type IN ('brand', 'store')",
            name="ck_staff_scope_assignment_scope_type",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_staff_scope_assignment_status",
        ),
        CheckConstraint(
            "(scope_type = 'brand' AND scope_id IS NULL AND role IN ('brand_admin', 'hq_operator')) OR "
            "(scope_type = 'store' AND scope_id IS NOT NULL AND role IN ('store_manager', 'store_staff'))",
            name="ck_staff_scope_assignment_role_scope",
        ),
        Index(
            "uq_staff_scope_assignment_active_brand",
            "staff_id",
            "role",
            unique=True,
            postgresql_where=text("scope_type = 'brand' AND status = 'active'"),
            sqlite_where=text("scope_type = 'brand' AND status = 'active'"),
        ),
        Index(
            "uq_staff_scope_assignment_active_store",
            "staff_id",
            "role",
            "scope_id",
            unique=True,
            postgresql_where=text("scope_type = 'store' AND status = 'active'"),
            sqlite_where=text("scope_type = 'store' AND status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(16), index=True)
    scope_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_by_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
