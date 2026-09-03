"""Add optional expiry for temporary staff accounts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_staff_expiry"
down_revision: Union[str, None] = "20260825_profile_corrections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("staff")}
    if "temporary_expires_at" not in columns:
        op.add_column("staff", sa.Column("temporary_expires_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("staff")}
    if "ix_staff_temporary_expires_at" not in indexes:
        op.create_index("ix_staff_temporary_expires_at", "staff", ["temporary_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_staff_temporary_expires_at", table_name="staff")
    op.drop_column("staff", "temporary_expires_at")
