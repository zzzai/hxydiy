"""Allow manager identities without inventing a technician profile."""

from alembic import op
import sqlalchemy as sa

revision = '20261018_wecom_store_manager'
down_revision = '20261017_wecom_technician'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('staff_external_identities') as batch:
        batch.alter_column('technician_id', existing_type=sa.Integer(), existing_nullable=False, nullable=True)


def downgrade() -> None:
    identities = sa.table('staff_external_identities', sa.column('technician_id'))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(identities).where(identities.c.technician_id.is_(None))):
        raise RuntimeError('Manager identities exist; preserve data and roll back the application only')
    with op.batch_alter_table('staff_external_identities') as batch:
        batch.alter_column('technician_id', existing_type=sa.Integer(), existing_nullable=True, nullable=False)
