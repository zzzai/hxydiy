"""Add auditable service waivers and offline refund notes."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260814_settlement_p0"
down_revision: Union[str, None] = "20260814_customer_identity_p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlement_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=True),
        sa.Column("adjustment_type", sa.String(length=24), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("original_amount_cents", sa.Integer(), nullable=False),
        sa.Column("final_amount_cents", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("responsibility", sa.String(length=24), nullable=False, server_default="other"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="registered"),
        sa.Column("payment_allocation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("actor_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("store_id", "order_id", "selection_session_id", "adjustment_type", "reason_code", "responsibility", "status", "actor_staff_id"):
        op.create_index(f"ix_settlement_adjustments_{column}", "settlement_adjustments", [column])


def downgrade() -> None:
    op.drop_table("settlement_adjustments")
