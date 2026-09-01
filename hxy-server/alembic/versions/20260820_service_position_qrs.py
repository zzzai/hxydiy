"""Add persistent service-position QR bindings."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260820_service_position_qrs"
down_revision: Union[str, None] = "20260820_store_space_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_position_qrs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="personal_qr"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("replaced_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["service_position_qrs.id"]),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_service_position_qrs_public_id", "service_position_qrs", ["public_id"], unique=True)
    op.create_index("ix_service_position_qrs_store_id", "service_position_qrs", ["store_id"])
    op.create_index("ix_service_position_qrs_room_id", "service_position_qrs", ["room_id"])
    op.create_index("ix_service_position_qrs_status", "service_position_qrs", ["status"])
    op.create_index("ix_service_position_qrs_replaced_by_id", "service_position_qrs", ["replaced_by_id"])
    op.create_index(
        "uq_service_position_qrs_active_room",
        "service_position_qrs",
        ["room_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_service_position_qrs_active_room", table_name="service_position_qrs")
    op.drop_index("ix_service_position_qrs_replaced_by_id", table_name="service_position_qrs")
    op.drop_index("ix_service_position_qrs_status", table_name="service_position_qrs")
    op.drop_index("ix_service_position_qrs_room_id", table_name="service_position_qrs")
    op.drop_index("ix_service_position_qrs_store_id", table_name="service_position_qrs")
    op.drop_index("ix_service_position_qrs_public_id", table_name="service_position_qrs")
    op.drop_table("service_position_qrs")
