"""Add technician portal identity, invite and leave lifecycle tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_technician_portal"
# Keep the migration graph rooted in the tracked production head.  The
# intermediate development-only staff-expiry revision is not shipped.
down_revision: Union[str, None] = "20260815_member_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("staff")}
    if "technician_id" not in columns:
        op.add_column("staff", sa.Column("technician_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_staff_technician_id", "staff", "technicians", ["technician_id"], ["id"])
        op.create_unique_constraint("uq_staff_technician_id", "staff", ["technician_id"])
        op.create_index("ix_staff_technician_id", "staff", ["technician_id"])
    tables = set(inspector.get_table_names())
    if "technician_invites" not in tables:
        op.create_table("technician_invites", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False), sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True)), sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("technician_id"), sa.UniqueConstraint("staff_id"), sa.UniqueConstraint("token_hash"))
    if "technician_leave_requests" not in tables:
        op.create_table("technician_leave_requests", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False), sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date(), nullable=False), sa.Column("reason", sa.Text(), server_default="", nullable=False), sa.Column("status", sa.String(16), server_default="submitted", nullable=False), sa.Column("reviewed_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id")), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("review_note", sa.Text(), server_default="", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_table("technician_leave_requests")
    op.drop_table("technician_invites")
    op.drop_index("ix_staff_technician_id", table_name="staff")
    op.drop_constraint("uq_staff_technician_id", "staff", type_="unique")
    op.drop_constraint("fk_staff_technician_id", "staff", type_="foreignkey")
    op.drop_column("staff", "technician_id")
