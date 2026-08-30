"""Add the first-store service execution facts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_business_closure"
down_revision: Union[str, None] = "20260805_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("arrived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_visits_store_id", "visits", ["store_id"])
    op.create_index("ix_visits_order_id", "visits", ["order_id"], unique=True)
    op.create_index("ix_visits_user_id", "visits", ["user_id"])
    op.create_index("ix_visits_source", "visits", ["source"])
    op.create_index("ix_visits_status", "visits", ["status"])

    op.create_table(
        "service_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("visit_id", sa.Integer(), sa.ForeignKey("visits.id"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total_amount_cents", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_service_orders_store_id", "service_orders", ["store_id"])
    op.create_index("ix_service_orders_order_id", "service_orders", ["order_id"])
    op.create_index("ix_service_orders_visit_id", "service_orders", ["visit_id"], unique=True)
    op.create_index("ix_service_orders_status", "service_orders", ["status"])

    op.create_table(
        "service_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("service_order_id", sa.Integer(), sa.ForeignKey("service_orders.id"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("project_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_service_assignments_store_id", "service_assignments", ["store_id"])
    op.create_index("ix_service_assignments_service_order_id", "service_assignments", ["service_order_id"])
    op.create_index("ix_service_assignments_technician_id", "service_assignments", ["technician_id"])
    op.create_index("ix_service_assignments_room_id", "service_assignments", ["room_id"])
    op.create_index("ix_service_assignments_status", "service_assignments", ["status"])

    op.create_table(
        "state_transitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "idempotency_key", name="uq_transition_store_idempotency"),
    )
    op.create_index("ix_state_transitions_store_id", "state_transitions", ["store_id"])
    op.create_index("ix_state_transitions_entity_type", "state_transitions", ["entity_type"])
    op.create_index("ix_state_transitions_action", "state_transitions", ["action"])


def downgrade() -> None:
    op.drop_index("ix_state_transitions_action", table_name="state_transitions")
    op.drop_index("ix_state_transitions_entity_type", table_name="state_transitions")
    op.drop_index("ix_state_transitions_store_id", table_name="state_transitions")
    op.drop_table("state_transitions")

    op.drop_index("ix_service_assignments_status", table_name="service_assignments")
    op.drop_index("ix_service_assignments_room_id", table_name="service_assignments")
    op.drop_index("ix_service_assignments_technician_id", table_name="service_assignments")
    op.drop_index("ix_service_assignments_service_order_id", table_name="service_assignments")
    op.drop_index("ix_service_assignments_store_id", table_name="service_assignments")
    op.drop_table("service_assignments")

    op.drop_index("ix_service_orders_status", table_name="service_orders")
    op.drop_index("ix_service_orders_visit_id", table_name="service_orders")
    op.drop_index("ix_service_orders_order_id", table_name="service_orders")
    op.drop_index("ix_service_orders_store_id", table_name="service_orders")
    op.drop_table("service_orders")

    op.drop_index("ix_visits_status", table_name="visits")
    op.drop_index("ix_visits_source", table_name="visits")
    op.drop_index("ix_visits_user_id", table_name="visits")
    op.drop_index("ix_visits_order_id", table_name="visits")
    op.drop_index("ix_visits_store_id", table_name="visits")
    op.drop_table("visits")
