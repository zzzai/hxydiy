"""Add inspection follow-up evidence links and delivery receipts."""
import sqlalchemy as sa
from alembic import op


revision = "20261126_inspection_workflow"
down_revision = "20261126_inspection_areas"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("inspection_followups",
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"), primary_key=True, autoincrement=False),
        sa.Column("root_id", sa.Integer(), sa.ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("root_id", "sequence", name="uq_inspection_followup_sequence"),
        sa.CheckConstraint("sequence > 0 AND root_id <> review_id", name="ck_inspection_followup_sequence"),
    )
    op.create_table("inspection_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column("binding_id", sa.Integer(), sa.ForeignKey("staff_external_identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("binding_version", sa.Integer(), nullable=False),
        sa.Column("root_id", sa.Integer(), sa.ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE")),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("daily_area_photo_reviews.id", ondelete="CASCADE")),
        sa.Column("week_start", sa.Date()),
        sa.Column("summary_text", sa.Text()),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", "binding_id", name="uq_inspection_delivery_recipient"),
        sa.CheckConstraint("state IN ('pending','sending','accepted','rejected','unknown','cancelled')",
                           name="ck_inspection_delivery_state"),
    )
    op.create_index("ix_inspection_deliveries_state", "inspection_deliveries", ["state"])


def downgrade():
    db = op.get_bind()
    for table in ("inspection_followups", "inspection_deliveries"):
        if db.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Inspection history is present; refusing destructive downgrade.")
    op.drop_table("inspection_deliveries")
    op.drop_table("inspection_followups")
