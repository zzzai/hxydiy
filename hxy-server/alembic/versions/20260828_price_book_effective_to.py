"""Add validity end timestamps to project price history."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_price_book_effective_to"
down_revision: Union[str, Sequence[str], None] = "20260828_tech_acct_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("price_book")}
    if "effective_to" not in columns:
        op.add_column("price_book", sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("price_book")}
    if "effective_to" in columns:
        op.drop_column("price_book", "effective_to")
