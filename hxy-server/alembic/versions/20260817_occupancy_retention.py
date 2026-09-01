"""Add occupancy retention deadline."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260817_occupancy_retention"
down_revision: Union[str, None] = "20260815_member_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("position_occupancies") as batch_op:
        batch_op.add_column(
            sa.Column("retained_until", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_index(
        "ix_position_occupancies_retained_until",
        "position_occupancies",
        ["retained_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_occupancies_retained_until",
        table_name="position_occupancies",
    )
    with op.batch_alter_table("position_occupancies") as batch_op:
        batch_op.drop_column("retained_until")
