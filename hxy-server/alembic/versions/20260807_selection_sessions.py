"""Add anonymous in-store DIY selection sessions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_selection_sessions"
down_revision: Union[str, None] = "20260805_business_closure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "selection_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("device_label", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("diy_preferences", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_selection_sessions_access_token_hash", "selection_sessions", ["access_token_hash"])
    op.create_index("ix_selection_sessions_store_id", "selection_sessions", ["store_id"])
    op.create_index("ix_selection_sessions_customer_id", "selection_sessions", ["customer_id"])
    op.create_index("ix_selection_sessions_status", "selection_sessions", ["status"])
    op.create_index("ix_selection_sessions_expires_at", "selection_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_selection_sessions_expires_at", table_name="selection_sessions")
    op.drop_index("ix_selection_sessions_status", table_name="selection_sessions")
    op.drop_index("ix_selection_sessions_customer_id", table_name="selection_sessions")
    op.drop_index("ix_selection_sessions_store_id", table_name="selection_sessions")
    op.drop_index("ix_selection_sessions_access_token_hash", table_name="selection_sessions")
    op.drop_table("selection_sessions")
