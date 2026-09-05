"""customer single device login

Revision ID: 20260905_customer_single_session
Revises: 20260904_service_reference_v2
"""
from alembic import op
import sqlalchemy as sa

revision = "20260905_customer_single_session"
down_revision = "20260904_service_reference_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("customer_login_version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "customer_login_version")
