"""Add manager daily check-ins, area photos, meeting recordings and assessments."""

from alembic import op
import sqlalchemy as sa

revision = "20261109_daily_manager_ops"
down_revision = "20261027_staff_learning"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_store_checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("manager_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "business_date", name="uq_daily_store_checkin_date"),
        sa.CheckConstraint("status IN ('draft', 'submitted')", name="ck_daily_store_checkin_status"),
    )
    op.create_index("ix_daily_store_checkins_store_id", "daily_store_checkins", ["store_id"])
    op.create_index("ix_daily_store_checkins_business_date", "daily_store_checkins", ["business_date"])

    op.create_table(
        "daily_area_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checkin_id", sa.Integer(), sa.ForeignKey("daily_store_checkins.id"), nullable=False),
        sa.Column("area", sa.String(24), nullable=False),
        sa.Column("media_id", sa.Integer(), sa.ForeignKey("media_assets.id"), nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("checkin_id", "area", name="uq_daily_area_photo_area"),
        sa.CheckConstraint(
            "area IN ('restroom', 'water_room', 'cashier', 'rest_area', 'foot_area')",
            name="ck_daily_area_photo_area",
        ),
    )
    op.create_index("ix_daily_area_photos_checkin_id", "daily_area_photos", ["checkin_id"])

    op.create_table(
        "daily_meeting_recordings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checkin_id", sa.Integer(), sa.ForeignKey("daily_store_checkins.id"), nullable=False),
        sa.Column("media_id", sa.Integer(), sa.ForeignKey("media_assets.id"), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("attendees", sa.String(300), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("transcript_status", sa.String(24), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("asr_provider", sa.String(24), nullable=False),
        sa.Column("asr_task_id", sa.String(128), nullable=False),
        sa.Column("error_message", sa.String(500), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "transcript_status IN ('uploaded', 'transcribing', 'transcribed', 'failed', 'not_configured')",
            name="ck_daily_meeting_transcript_status",
        ),
    )
    op.create_index("ix_daily_meeting_recordings_checkin_id", "daily_meeting_recordings", ["checkin_id"])
    op.create_index("ix_daily_meeting_recordings_transcript_status", "daily_meeting_recordings", ["transcript_status"])
    op.create_index("ix_daily_meeting_recordings_retention_until", "daily_meeting_recordings", ["retention_until"])

    op.create_table(
        "training_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("staff_learning_assignments.id"), nullable=True),
        sa.Column("course_name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("manager_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("manager_note", sa.String(500), nullable=False),
        sa.Column("manager_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hq_status", sa.String(16), nullable=False),
        sa.Column("hq_reviewer_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("hq_note", sa.String(500), nullable=False),
        sa.Column("hq_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('theory', 'practical')", name="ck_training_assessment_kind"),
        sa.CheckConstraint("result IN ('pending', 'passed', 'failed')", name="ck_training_assessment_result"),
        sa.CheckConstraint("hq_status IN ('pending', 'passed', 'returned')", name="ck_training_assessment_hq_status"),
    )
    op.create_index("ix_training_assessments_store_id", "training_assessments", ["store_id"])
    op.create_index("ix_training_assessments_staff_id", "training_assessments", ["staff_id"])
    op.create_index("ix_training_assessments_assignment_id", "training_assessments", ["assignment_id"])
    op.create_index("ix_training_assessments_store_staff", "training_assessments", ["store_id", "staff_id"])
    op.create_index("ix_training_assessments_hq_status", "training_assessments", ["hq_status"])


def downgrade():
    op.drop_table("training_assessments")
    op.drop_table("daily_meeting_recordings")
    op.drop_table("daily_area_photos")
    op.drop_table("daily_store_checkins")
