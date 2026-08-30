"""Add store scope to SCRM definitions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_scrm_store_scope"
down_revision: Union[str, None] = "20260825_membership_store_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("customer_tags", "customer_segments", "automation_rules"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "store_id" not in columns:
            op.add_column(table, sa.Column("store_id", sa.Integer(), nullable=True))
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        index_name = f"ix_{table}_store_id"
        if index_name not in indexes:
            op.create_index(index_name, table, ["store_id"])
        if bind.dialect.name != "sqlite":
            constraint_name = f"fk_{table}_store_id"
            existing = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table)}
            if constraint_name not in existing:
                op.create_foreign_key(constraint_name, table, "stores", ["store_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("automation_rules", "customer_segments", "customer_tags"):
        index_name = f"ix_{table}_store_id"
        if index_name in {index["name"] for index in sa.inspect(bind).get_indexes(table)}:
            op.drop_index(index_name, table_name=table)
        if bind.dialect.name != "sqlite":
            constraint_name = f"fk_{table}_store_id"
            if constraint_name in {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table)}:
                op.drop_constraint(constraint_name, table, type_="foreignkey")
        op.drop_column(table, "store_id")
