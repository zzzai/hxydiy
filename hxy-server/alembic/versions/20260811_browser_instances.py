"""Add first-party anonymous browser continuity."""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20260811_browser_instances"
down_revision: Union[str, None] = "20260810_page_contents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "browser_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_browser_instances_token_hash"),
    )
    op.create_index("ix_browser_instances_token_hash", "browser_instances", ["token_hash"])
    op.create_index("ix_browser_instances_customer_id", "browser_instances", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_browser_instances_customer_id", table_name="browser_instances")
    op.drop_index("ix_browser_instances_token_hash", table_name="browser_instances")
    op.drop_table("browser_instances")
