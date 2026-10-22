"""Persistent operational exception queue for store workbench."""

from alembic import op
import sqlalchemy as sa

revision = '20261023_operational_exceptions'
down_revision = '20261023_page_content_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'operational_exceptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('exception_type', sa.String(length=48), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('dedupe_key', sa.String(length=160), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=False),
        sa.Column('resolution_note', sa.String(length=500), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'dedupe_key', name='uq_operational_exceptions_store_key'),
    )
    op.create_index('ix_operational_exceptions_store_id', 'operational_exceptions', ['store_id'])
    op.create_index('ix_operational_exceptions_exception_type', 'operational_exceptions', ['exception_type'])
    op.create_index('ix_operational_exceptions_status', 'operational_exceptions', ['status'])


def downgrade() -> None:
    op.drop_index('ix_operational_exceptions_status', table_name='operational_exceptions')
    op.drop_index('ix_operational_exceptions_exception_type', table_name='operational_exceptions')
    op.drop_index('ix_operational_exceptions_store_id', table_name='operational_exceptions')
    op.drop_table('operational_exceptions')
