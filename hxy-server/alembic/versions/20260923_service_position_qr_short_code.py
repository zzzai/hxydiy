"""Add hashed short codes for service-position QR links."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260923_qr_short_code"
down_revision: Union[str, None] = "20260921_staff_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "service_position_qrs",
        sa.Column("short_code_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_service_position_qrs_short_code_hash",
        "service_position_qrs",
        ["short_code_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_service_position_qrs_short_code_hash", table_name="service_position_qrs")
    op.drop_column("service_position_qrs", "short_code_hash")
