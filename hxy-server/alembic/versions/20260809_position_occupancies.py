"""Add service-position static fields and independent occupancies."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_position_occupancies"
down_revision: Union[str, None] = "20260807_selection_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("customer_label", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("rooms", sa.Column("map_x", sa.Float(), nullable=False, server_default="0"))
    op.add_column("rooms", sa.Column("map_y", sa.Float(), nullable=False, server_default="0"))
    op.add_column("rooms", sa.Column("map_width", sa.Float(), nullable=False, server_default="0.2"))
    op.add_column("rooms", sa.Column("map_height", sa.Float(), nullable=False, server_default="0.13"))
    op.add_column("rooms", sa.Column("customer_selectable", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("rooms", sa.Column("operational_status", sa.String(length=16), nullable=False, server_default="active"))
    op.add_column("rooms", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_rooms_operational_status", "rooms", ["operational_status"])

    op.add_column("selection_sessions", sa.Column("pricing_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("selection_sessions", sa.Column("store_total_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("selection_sessions", sa.Column("member_total_cents", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "position_occupancies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("active_room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column("active_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="held"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="personal_qr"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_service_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("active_room_id", name="uq_position_occupancy_active_room"),
        sa.UniqueConstraint("active_session_id", name="uq_position_occupancy_active_session"),
    )
    op.create_index("ix_position_occupancies_store_id", "position_occupancies", ["store_id"])
    op.create_index("ix_position_occupancies_room_id", "position_occupancies", ["room_id"])
    op.create_index("ix_position_occupancies_selection_session_id", "position_occupancies", ["selection_session_id"])
    op.create_index("ix_position_occupancies_status", "position_occupancies", ["status"])
    op.create_index("ix_position_occupancies_hold_expires_at", "position_occupancies", ["hold_expires_at"])


def downgrade() -> None:
    op.drop_table("position_occupancies")
    op.drop_column("selection_sessions", "member_total_cents")
    op.drop_column("selection_sessions", "store_total_cents")
    op.drop_column("selection_sessions", "pricing_snapshot")
    op.drop_index("ix_rooms_operational_status", table_name="rooms")
    for column in (
        "version", "operational_status", "customer_selectable", "map_height",
        "map_width", "map_y", "map_x", "customer_label",
    ):
        op.drop_column("rooms", column)
