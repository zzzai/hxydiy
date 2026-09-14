"""Add membership-cycle closure metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260910_membership_closure"
down_revision: Union[str, None] = "20260906_wellness_current"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table_name = "membership_benefit_grants"
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("benefit_type", sa.String(length=32), nullable=False, server_default="annual_project_gift"),
            sa.Column("membership_cycle_id", sa.String(length=64), nullable=False),
            sa.Column("membership_started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("membership_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
            sa.Column("cycle_state", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("payment_channel", sa.String(length=32), nullable=True),
            sa.Column("payment_reference", sa.String(length=64), nullable=True),
            sa.Column("rights_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_reason", sa.String(length=200), nullable=True),
            sa.Column("refund_disposition", sa.String(length=64), nullable=True),
            sa.Column("recovery_idempotency_key", sa.String(length=64), nullable=True),
            sa.Column("redemption_idempotency_key", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="available"),
            sa.Column("used_service_line_id", sa.String(length=36), sa.ForeignKey("service_lines.id"), nullable=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "membership_cycle_id", name="uq_membership_benefit_cycle"),
            sa.UniqueConstraint("used_service_line_id", name="uq_membership_benefit_used_service_line"),
            sa.UniqueConstraint("recovery_idempotency_key", name="uq_membership_benefit_recovery_key"),
            sa.UniqueConstraint("redemption_idempotency_key", name="uq_membership_benefit_redemption_key"),
            sa.CheckConstraint("status IN ('available', 'used', 'voided')", name="ck_membership_benefit_status"),
        )
        op.create_index("ix_membership_benefit_grants_user_id", table_name, ["user_id"])
        op.create_index("ix_membership_benefit_grants_status", table_name, ["status"])
        op.create_index("ix_membership_benefit_user_status", table_name, ["user_id", "status"])
        op.create_index("ix_membership_benefit_store_id", table_name, ["store_id"])
        op.create_index("ix_membership_benefit_cycle_state", table_name, ["cycle_state"])
        return

    columns = {
        "membership_expires_at": sa.Column("membership_expires_at", sa.DateTime(timezone=True), nullable=True),
        "store_id": sa.Column("store_id", sa.Integer(), nullable=True),
        "cycle_state": sa.Column("cycle_state", sa.String(length=16), nullable=False, server_default="active"),
        "payment_channel": sa.Column("payment_channel", sa.String(length=32), nullable=True),
        "payment_reference": sa.Column("payment_reference", sa.String(length=64), nullable=True),
        "rights_confirmed": sa.Column("rights_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        "cancelled_at": sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        "cancellation_reason": sa.Column("cancellation_reason", sa.String(length=200), nullable=True),
        "refund_disposition": sa.Column("refund_disposition", sa.String(length=64), nullable=True),
        "recovery_idempotency_key": sa.Column("recovery_idempotency_key", sa.String(length=64), nullable=True),
        "redemption_idempotency_key": sa.Column("redemption_idempotency_key", sa.String(length=64), nullable=True),
    }
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    for name, column in columns.items():
        if name not in existing_columns:
            op.add_column(table_name, column)

    inspector = sa.inspect(op.get_bind())
    unique_columns = {
        tuple(constraint.get("column_names") or [])
        for constraint in inspector.get_unique_constraints(table_name)
    }
    foreign_keys = {
        (tuple(foreign_key.get("constrained_columns") or []), foreign_key.get("referred_table"))
        for foreign_key in inspector.get_foreign_keys(table_name)
    }
    needs_recovery_key = ("recovery_idempotency_key",) not in unique_columns
    needs_redemption_key = ("redemption_idempotency_key",) not in unique_columns
    needs_store_fk = (("store_id",), "stores") not in foreign_keys
    if needs_recovery_key or needs_redemption_key or needs_store_fk:
        with op.batch_alter_table(table_name) as batch_op:
            if needs_recovery_key:
                batch_op.create_unique_constraint("uq_membership_benefit_recovery_key", ["recovery_idempotency_key"])
            if needs_redemption_key:
                batch_op.create_unique_constraint("uq_membership_benefit_redemption_key", ["redemption_idempotency_key"])
            if needs_store_fk:
                batch_op.create_foreign_key("fk_membership_benefit_store_id", "stores", ["store_id"], ["id"])

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if "ix_membership_benefit_store_id" not in indexes:
        op.create_index("ix_membership_benefit_store_id", table_name, ["store_id"])
    if "ix_membership_benefit_cycle_state" not in indexes:
        op.create_index("ix_membership_benefit_cycle_state", table_name, ["cycle_state"])


def downgrade() -> None:
    op.drop_index("ix_membership_benefit_cycle_state", table_name="membership_benefit_grants")
    op.drop_index("ix_membership_benefit_store_id", table_name="membership_benefit_grants")
    with op.batch_alter_table("membership_benefit_grants") as batch_op:
        batch_op.drop_constraint("fk_membership_benefit_store_id", type_="foreignkey")
        batch_op.drop_constraint("uq_membership_benefit_redemption_key", type_="unique")
        batch_op.drop_column("redemption_idempotency_key")
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
