"""Add exception owner, SLA due time and acknowledgement."""

from alembic import op
import sqlalchemy as sa

revision = '20261025_exception_owner'
down_revision = '20261024_technician_shifts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('operational_exceptions') as batch:
        batch.add_column(sa.Column('assigned_staff_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('due_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_operational_exceptions_assigned_staff', 'staff', ['assigned_staff_id'], ['id'])
        batch.create_index('ix_operational_exceptions_assigned_staff_id', ['assigned_staff_id'])


def downgrade() -> None:
    with op.batch_alter_table('operational_exceptions') as batch:
        batch.drop_index('ix_operational_exceptions_assigned_staff_id')
        batch.drop_constraint('fk_operational_exceptions_assigned_staff', type_='foreignkey')
        batch.drop_column('acknowledged_at')
        batch.drop_column('due_at')
        batch.drop_column('assigned_staff_id')
