"""Reconcile SMS receipt columns for databases upgraded through the former local chain."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_sms_receipt_reconcile"
down_revision: Union[str, None] = "20260821_feedback_follow_up"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns("customer_verification_codes")
    }
    missing_biz_id = "sms_biz_id" not in columns
    missing_request_id = "sms_request_id" not in columns
    if missing_biz_id or missing_request_id:
        with op.batch_alter_table("customer_verification_codes") as batch_op:
            if missing_biz_id:
                batch_op.add_column(
                    sa.Column("sms_biz_id", sa.String(length=64), nullable=True)
                )
            if missing_request_id:
                batch_op.add_column(
                    sa.Column("sms_request_id", sa.String(length=64), nullable=True)
                )

    indexes = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("customer_verification_codes")
    }
    if "ix_customer_verification_codes_sms_biz_id" not in indexes:
        op.create_index(
            "ix_customer_verification_codes_sms_biz_id",
            "customer_verification_codes",
            ["sms_biz_id"],
        )


def downgrade() -> None:
    # The columns belong to the historical 20260819 revision. This repair migration
    # must not remove them when rolling back only the reconciliation step.
    pass
