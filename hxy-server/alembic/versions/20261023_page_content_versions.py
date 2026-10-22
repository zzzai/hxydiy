"""Store page publication snapshots for history and rollback."""

from alembic import op
import sqlalchemy as sa

revision = '20261023_page_content_versions'
down_revision = '20261018_wecom_store_manager'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'page_content_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('page_key', sa.String(length=64), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_by_staff_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'page_key', 'version_no', name='uq_page_content_versions_store_key_version'),
    )
    op.create_index('ix_page_content_versions_store_id', 'page_content_versions', ['store_id'])
    op.create_index('ix_page_content_versions_page_key', 'page_content_versions', ['page_key'])


def downgrade() -> None:
    op.drop_index('ix_page_content_versions_page_key', table_name='page_content_versions')
    op.drop_index('ix_page_content_versions_store_id', table_name='page_content_versions')
    op.drop_table('page_content_versions')
