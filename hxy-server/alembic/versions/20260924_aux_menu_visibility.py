"""Allow published projects to remain linked without appearing as standalone menu items."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260924_aux_visibility"
down_revision: Union[str, None] = "20260923_qr_short_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "independently_visible" not in columns:
        op.add_column(
            "projects",
            sa.Column("independently_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "independently_visible" in columns:
        op.drop_column("projects", "independently_visible")
