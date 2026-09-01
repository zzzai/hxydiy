"""Link a DIY selection to its front-desk service execution flow."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_diy_counter_checkout"
down_revision: Union[str, None] = "20260811_service_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("selection_sessions") as batch:
        batch.add_column(sa.Column("fulfillment_order_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_selection_sessions_fulfillment_order_id",
            "orders",
            ["fulfillment_order_id"],
            ["id"],
        )
        batch.create_index(
            "ix_selection_sessions_fulfillment_order_id",
            ["fulfillment_order_id"],
            unique=True,
        )
    with op.batch_alter_table("visits") as batch:
        batch.add_column(sa.Column("selection_session_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_visits_selection_session_id",
            "selection_sessions",
            ["selection_session_id"],
            ["id"],
        )
        batch.create_index(
            "ix_visits_selection_session_id",
            ["selection_session_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("visits") as batch:
        batch.drop_index("ix_visits_selection_session_id")
        batch.drop_constraint("fk_visits_selection_session_id", type_="foreignkey")
        batch.drop_column("selection_session_id")
    with op.batch_alter_table("selection_sessions") as batch:
        batch.drop_index("ix_selection_sessions_fulfillment_order_id")
        batch.drop_constraint("fk_selection_sessions_fulfillment_order_id", type_="foreignkey")
        batch.drop_column("fulfillment_order_id")
