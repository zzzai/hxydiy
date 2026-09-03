"""Add service feedback follow-up workflow."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_feedback_follow_up"
down_revision: Union[str, None] = "20260820_service_position_qrs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("service_feedback") as batch:
        batch.add_column(
            sa.Column(
                "follow_up_status",
                sa.String(length=16),
                nullable=False,
                server_default="open",
            )
        )
        batch.add_column(sa.Column("follow_up_staff_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "follow_up_note",
                sa.String(length=1000),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column("followed_up_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_index("ix_service_feedback_follow_up_status", ["follow_up_status"])
        batch.create_index("ix_service_feedback_follow_up_staff_id", ["follow_up_staff_id"])
        batch.create_foreign_key(
            "fk_service_feedback_follow_up_staff_id",
            "staff",
            ["follow_up_staff_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("service_feedback") as batch:
        batch.drop_constraint("fk_service_feedback_follow_up_staff_id", type_="foreignkey")
        batch.drop_index("ix_service_feedback_follow_up_staff_id")
        batch.drop_index("ix_service_feedback_follow_up_status")
        batch.drop_column("followed_up_at")
        batch.drop_column("follow_up_note")
        batch.drop_column("follow_up_staff_id")
        batch.drop_column("follow_up_status")
