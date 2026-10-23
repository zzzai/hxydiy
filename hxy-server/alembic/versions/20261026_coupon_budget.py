"""Add optional coupon budget."""

from alembic import op
import sqlalchemy as sa

revision = '20261026_coupon_budget'
down_revision = '20261023_store_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'coupon_templates' not in inspector.get_table_names():
        return
    if 'budget_cents' in {column['name'] for column in inspector.get_columns('coupon_templates')}:
        return
    with op.batch_alter_table('coupon_templates') as batch:
        batch.add_column(sa.Column('budget_cents', sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'coupon_templates' not in inspector.get_table_names():
        return
    if 'budget_cents' not in {column['name'] for column in inspector.get_columns('coupon_templates')}:
        return
    with op.batch_alter_table('coupon_templates') as batch:
        batch.drop_column('budget_cents')
