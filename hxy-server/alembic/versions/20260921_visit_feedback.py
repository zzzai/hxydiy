"""Add independently persisted visit feedback."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260921_visit_feedback"
down_revision: Union[str, None] = "20260921_product_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "visit_feedback" in inspector.get_table_names():
        return
    op.create_table(
        "visit_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("service_position_qr_id", sa.Integer(), sa.ForeignKey("service_position_qrs.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("follow_up_status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("follow_up_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("follow_up_note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("followed_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_visit_feedback_rating"),
        sa.CheckConstraint(
            "follow_up_status IN ('open', 'in_progress', 'resolved', 'dismissed')",
            name="ck_visit_feedback_follow_up_status",
        ),
        sa.UniqueConstraint("identity_hash", "idempotency_key_hash", name="uq_visit_feedback_identity_key"),
    )
    op.create_index("ix_visit_feedback_store_id", "visit_feedback", ["store_id"])
    op.create_index("ix_visit_feedback_room_id", "visit_feedback", ["room_id"])
    op.create_index("ix_visit_feedback_service_position_qr_id", "visit_feedback", ["service_position_qr_id"])
    op.create_index("ix_visit_feedback_customer_id", "visit_feedback", ["customer_id"])
    op.create_index("ix_visit_feedback_follow_up_status", "visit_feedback", ["follow_up_status"])
    op.create_index("ix_visit_feedback_follow_up_staff_id", "visit_feedback", ["follow_up_staff_id"])
    op.create_index("ix_visit_feedback_created_at", "visit_feedback", ["created_at"])
    op.create_index(
        "ix_visit_feedback_rate_scope",
        "visit_feedback",
        ["identity_hash", "service_position_qr_id", "created_at"],
    )


def downgrade() -> None:
    if "visit_feedback" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("visit_feedback")
