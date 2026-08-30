"""Add explicit room-container and service-position hierarchy."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260820_store_space_hierarchy"
down_revision: Union[str, None] = "20260819_sms_send_receipts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("parent_room_id", sa.Integer(), nullable=True))
    op.add_column("rooms", sa.Column("is_space_container", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("rooms", sa.Column("is_service_position", sa.Boolean(), nullable=False, server_default=sa.true()))
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key("fk_rooms_parent_room_id", "rooms", "rooms", ["parent_room_id"], ["id"])
    op.create_index("ix_rooms_parent_room_id", "rooms", ["parent_room_id"])
    op.create_index("ix_rooms_is_space_container", "rooms", ["is_space_container"])
    op.create_index("ix_rooms_is_service_position", "rooms", ["is_service_position"])


def downgrade() -> None:
    op.drop_index("ix_rooms_is_service_position", table_name="rooms")
    op.drop_index("ix_rooms_is_space_container", table_name="rooms")
    op.drop_index("ix_rooms_parent_room_id", table_name="rooms")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_rooms_parent_room_id", "rooms", type_="foreignkey")
    op.drop_column("rooms", "is_service_position")
    op.drop_column("rooms", "is_space_container")
    op.drop_column("rooms", "parent_room_id")
