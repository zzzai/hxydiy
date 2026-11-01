"""Add isolated staff learning facts; no changes to existing business rows."""

from alembic import op
import sqlalchemy as sa

revision = "20261027_staff_learning"
down_revision = "20261026_coupon_budget"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learning_course_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("version", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("approval_reference", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_learning_course_version"),
        sa.CheckConstraint("status IN ('pilot', 'published', 'retired')", name="ck_learning_course_status"))
    op.create_table("staff_learning_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("staff_name", sa.String(32), nullable=False),
        sa.Column("course_version_id", sa.String(36), sa.ForeignKey("learning_course_versions.id"), nullable=False),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sections_read", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("store_id", "staff_id", "course_version_id", name="uq_staff_learning_assignment"),
        sa.CheckConstraint("revision >= 0", name="ck_staff_learning_revision"))
    op.create_index("ix_staff_learning_assignments_store_id", "staff_learning_assignments", ["store_id"])
    op.create_index("ix_staff_learning_assignments_staff_id", "staff_learning_assignments", ["staff_id"])
    op.create_table("staff_learning_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("staff_learning_assignments.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("actor_name", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("assignment_revision", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "actor_id", "request_id", name="uq_staff_learning_request"),
        sa.CheckConstraint("kind IN ('assign', 'mark_section', 'submit', 'follow_up')", name="ck_staff_learning_event_kind"))
    for column in ("store_id", "assignment_id"):
        op.create_index("ix_staff_learning_events_" + column, "staff_learning_events", [column])


def downgrade():
    # Operator-only rollback: this removes learning history. Prefer disabling the feature after use.
    op.drop_table("staff_learning_events")
    op.drop_table("staff_learning_assignments")
    op.drop_table("learning_course_versions")
