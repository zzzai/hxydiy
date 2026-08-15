"""Add customer service feedback."""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20260811_service_feedback"
down_revision: Union[str, None] = "20260811_browser_instances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("selection_session_id", name="uq_service_feedback_session"),
    )
    op.create_index("ix_service_feedback_store_id", "service_feedback", ["store_id"])
    op.create_index("ix_service_feedback_selection_session_id", "service_feedback", ["selection_session_id"])
    op.create_index("ix_service_feedback_customer_id", "service_feedback", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_service_feedback_customer_id", table_name="service_feedback")
    op.drop_index("ix_service_feedback_selection_session_id", table_name="service_feedback")
    op.drop_index("ix_service_feedback_store_id", table_name="service_feedback")
    op.drop_table("service_feedback")
