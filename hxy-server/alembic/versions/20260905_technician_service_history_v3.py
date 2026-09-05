"""Persist the technician who actually serviced an occupancy."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_tech_history_v3"
down_revision = "20260904_service_reference_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    owner_column = sa.Column(
        "serviced_by_technician_id",
        sa.Integer(),
        sa.ForeignKey(
            "technicians.id",
            name="fk_position_occupancies_serviced_by_technician_id",
        ),
        nullable=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("position_occupancies") as batch_op:
            batch_op.add_column(owner_column)
    else:
        op.add_column("position_occupancies", owner_column)
    op.create_index(
        "ix_position_occupancies_serviced_by_technician_id",
        "position_occupancies",
        ["serviced_by_technician_id"],
    )
    op.create_index(
        "ix_position_occupancies_store_technician_finished",
        "position_occupancies",
        ["store_id", "serviced_by_technician_id", "actual_service_end_at"],
    )

    # Historical ownership is assigned only when every relevant technician action
    # for the occupancy resolves to one and the same explicit Staff-Technician link.
    # Missing, cross-store, unlinked, or multi-technician evidence remains NULL.
    op.execute(sa.text("""
        UPDATE position_occupancies
        SET serviced_by_technician_id = (
            SELECT MIN(staff.technician_id)
            FROM audit_logs
            JOIN staff ON CAST(staff.id AS VARCHAR) = audit_logs.actor_id
            WHERE audit_logs.actor_type = 'staff'
              AND audit_logs.entity_type = 'position_occupancy'
              AND audit_logs.entity_id = CAST(position_occupancies.id AS VARCHAR)
              AND audit_logs.action IN (
                  'technician_confirm_service',
                  'technician_finish_service'
              )
              AND audit_logs.store_id = position_occupancies.store_id
              AND staff.store_id = position_occupancies.store_id
              AND staff.technician_id IS NOT NULL
        )
        WHERE actual_service_end_at IS NOT NULL
          AND (
              SELECT COUNT(*)
              FROM audit_logs
              WHERE audit_logs.entity_type = 'position_occupancy'
                AND audit_logs.entity_id = CAST(position_occupancies.id AS VARCHAR)
                AND audit_logs.action IN (
                    'technician_confirm_service',
                    'technician_finish_service'
                )
          ) = (
              SELECT COUNT(*)
              FROM audit_logs
              JOIN staff ON CAST(staff.id AS VARCHAR) = audit_logs.actor_id
              WHERE audit_logs.actor_type = 'staff'
                AND audit_logs.entity_type = 'position_occupancy'
                AND audit_logs.entity_id = CAST(position_occupancies.id AS VARCHAR)
                AND audit_logs.action IN (
                    'technician_confirm_service',
                    'technician_finish_service'
                )
                AND audit_logs.store_id = position_occupancies.store_id
                AND staff.store_id = position_occupancies.store_id
                AND staff.technician_id IS NOT NULL
          )
          AND 1 = (
              SELECT COUNT(DISTINCT staff.technician_id)
              FROM audit_logs
              JOIN staff ON CAST(staff.id AS VARCHAR) = audit_logs.actor_id
              WHERE audit_logs.actor_type = 'staff'
                AND audit_logs.entity_type = 'position_occupancy'
                AND audit_logs.entity_id = CAST(position_occupancies.id AS VARCHAR)
                AND audit_logs.action IN (
                    'technician_confirm_service',
                    'technician_finish_service'
                )
                AND audit_logs.store_id = position_occupancies.store_id
                AND staff.store_id = position_occupancies.store_id
                AND staff.technician_id IS NOT NULL
          )
    """))


def downgrade() -> None:
    op.drop_index(
        "ix_position_occupancies_store_technician_finished",
        table_name="position_occupancies",
    )
    op.drop_index(
        "ix_position_occupancies_serviced_by_technician_id",
        table_name="position_occupancies",
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("position_occupancies") as batch_op:
            batch_op.drop_column("serviced_by_technician_id")
    else:
        op.drop_column("position_occupancies", "serviced_by_technician_id")
