"""Add bounded, version-specific store inspection photo reviews."""
import sqlalchemy as sa
from alembic import op

revision = "20261122_inspection_ai"
down_revision = "20261122_daily_photo_slots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_area_photo_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("photo_id", sa.Integer(), sa.ForeignKey("daily_area_photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.Integer(), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("rubric", sa.String(40), nullable=False),
        sa.Column("result", sa.JSON(none_as_null=True)),
        sa.Column("error_code", sa.String(32)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("manual_verdict", sa.String(12)),
        sa.Column("manual_staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="SET NULL")),
        sa.Column("manual_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("photo_id", "media_id", name="uq_inspection_review_photo_media"),
        sa.CheckConstraint("state IN ('pending','running','done','failed','superseded')", name="ck_inspection_review_state"),
        sa.CheckConstraint("manual_verdict IN ('pass','fix','retake')", name="ck_inspection_review_manual"),
    )
    op.create_index("ix_inspection_review_queue", "daily_area_photo_reviews", ["state", "id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM daily_area_photo_reviews")):
        raise RuntimeError("Cannot remove inspection reviews while records exist")
    op.drop_table("daily_area_photo_reviews")
