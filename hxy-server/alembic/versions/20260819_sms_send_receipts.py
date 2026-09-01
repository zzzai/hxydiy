"""Persist Alibaba Cloud SMS send references for delivery troubleshooting."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260819_sms_send_receipts"
down_revision: Union[str, None] = "20260817_occupancy_retention"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customer_verification_codes") as batch_op:
        batch_op.add_column(sa.Column("sms_biz_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("sms_request_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_customer_verification_codes_sms_biz_id",
        "customer_verification_codes",
        ["sms_biz_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_verification_codes_sms_biz_id",
        table_name="customer_verification_codes",
    )
    with op.batch_alter_table("customer_verification_codes") as batch_op:
        batch_op.drop_column("sms_request_id")
        batch_op.drop_column("sms_biz_id")
