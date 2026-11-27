"""Allow customers to leave a callback number for one visit review."""

import sqlalchemy as sa
from alembic import op

revision = "20261127_visit_callback_phone"
down_revision = "20261126_inspection_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("visit_feedback", sa.Column("callback_phone", sa.String(11), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE visit_feedback IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT 1 FROM visit_feedback WHERE callback_phone IS NOT NULL LIMIT 1")):
        raise RuntimeError("Cannot remove callback_phone while visit feedback contains callback numbers")
    op.drop_column("visit_feedback", "callback_phone")
