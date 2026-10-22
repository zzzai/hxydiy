"""Weekly technician shifts for store scheduling."""

from alembic import op
import sqlalchemy as sa

revision = '20261024_technician_shifts'
down_revision = '20261023_operational_exceptions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'technician_shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('technician_id', sa.Integer(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('shift_type', sa.String(length=16), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=False),
        sa.Column('created_by_staff_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id']),
        sa.ForeignKeyConstraint(['created_by_staff_id'], ['staff.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('technician_id', 'work_date', name='uq_technician_shifts_technician_date'),
    )
    op.create_index('ix_technician_shifts_store_id', 'technician_shifts', ['store_id'])
    op.create_index('ix_technician_shifts_technician_id', 'technician_shifts', ['technician_id'])
    op.create_index('ix_technician_shifts_work_date', 'technician_shifts', ['work_date'])


def downgrade() -> None:
    op.drop_index('ix_technician_shifts_work_date', table_name='technician_shifts')
    op.drop_index('ix_technician_shifts_technician_id', table_name='technician_shifts')
    op.drop_index('ix_technician_shifts_store_id', table_name='technician_shifts')
    op.drop_table('technician_shifts')
