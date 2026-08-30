"""Add H5 verification records and publishable DIY content fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260810_diy_content_auth"
down_revision: Union[str, None] = "20260809_position_occupancies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("detail_modules", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("projects", sa.Column("diy_options", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("projects", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_projects_display_order", "projects", ["display_order"])
    op.create_table(
        "customer_verification_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_customer_verification_codes_phone", "customer_verification_codes", ["phone"])
    op.create_index("ix_customer_verification_codes_sent_at", "customer_verification_codes", ["sent_at"])
    op.create_index("ix_customer_verification_codes_expires_at", "customer_verification_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_customer_verification_codes_expires_at", table_name="customer_verification_codes")
    op.drop_index("ix_customer_verification_codes_sent_at", table_name="customer_verification_codes")
    op.drop_index("ix_customer_verification_codes_phone", table_name="customer_verification_codes")
    op.drop_table("customer_verification_codes")
    op.drop_index("ix_projects_display_order", table_name="projects")
    op.drop_column("projects", "display_order")
    op.drop_column("projects", "diy_options")
    op.drop_column("projects", "detail_modules")
