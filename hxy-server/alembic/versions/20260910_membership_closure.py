"""Add membership-cycle closure metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260910_membership_closure"
down_revision: Union[str, None] = "20260906_wellness_current"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("membership_benefit_grants") as batch_op:
        batch_op.add_column(sa.Column("membership_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True))
        batch_op.add_column(sa.Column("cycle_state", sa.String(length=16), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("payment_channel", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("payment_reference", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("rights_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancellation_reason", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("refund_disposition", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("recovery_idempotency_key", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            "uq_membership_benefit_recovery_key", ["recovery_idempotency_key"]
        )
    op.create_index("ix_membership_benefit_store_id", "membership_benefit_grants", ["store_id"])
    op.create_index("ix_membership_benefit_cycle_state", "membership_benefit_grants", ["cycle_state"])


def downgrade() -> None:
    op.drop_index("ix_membership_benefit_cycle_state", table_name="membership_benefit_grants")
    op.drop_index("ix_membership_benefit_store_id", table_name="membership_benefit_grants")
    with op.batch_alter_table("membership_benefit_grants") as batch_op:
        batch_op.drop_constraint("uq_membership_benefit_recovery_key", type_="unique")
        batch_op.drop_column("recovery_idempotency_key")
        batch_op.drop_column("refund_disposition")
        batch_op.drop_column("cancellation_reason")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("rights_confirmed")
        batch_op.drop_column("payment_reference")
        batch_op.drop_column("payment_channel")
        batch_op.drop_column("cycle_state")
        batch_op.drop_column("store_id")
        batch_op.drop_column("membership_expires_at")
