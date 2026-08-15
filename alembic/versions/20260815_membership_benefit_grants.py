"""Add membership benefit grants."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_member_grants"
down_revision: Union[str, None] = "20260815_catalog_options"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "membership_benefit_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("benefit_type", sa.String(length=32), nullable=False, server_default="annual_project_gift"),
        sa.Column("membership_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="available"),
        sa.Column("used_service_line_id", sa.String(length=36), sa.ForeignKey("service_lines.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "benefit_type",
            "membership_started_at",
            name="uq_membership_benefit_cycle",
        ),
        sa.UniqueConstraint("used_service_line_id", name="uq_membership_benefit_used_service_line"),
        sa.CheckConstraint(
            "status IN ('available', 'used', 'voided')",
            name="ck_membership_benefit_status",
        ),
    )
    op.create_index("ix_membership_benefit_grants_user_id", "membership_benefit_grants", ["user_id"])
    op.create_index("ix_membership_benefit_grants_status", "membership_benefit_grants", ["status"])
    op.create_index(
        "ix_membership_benefit_user_status",
        "membership_benefit_grants",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("membership_benefit_grants")
