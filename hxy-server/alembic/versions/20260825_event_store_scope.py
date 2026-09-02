"""Add store scope to analytics events."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_event_store_scope"
down_revision: Union[str, None] = "20260825_scrm_store_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_logs")}
    if "store_id" not in columns:
        op.add_column("event_logs", sa.Column("store_id", sa.Integer(), nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("event_logs")}
    if "ix_event_logs_store_id" not in indexes:
        op.create_index("ix_event_logs_store_id", "event_logs", ["store_id"])
    if bind.dialect.name != "sqlite":
        existing = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("event_logs")}
        if "fk_event_logs_store_id" not in existing:
            op.create_foreign_key("fk_event_logs_store_id", "event_logs", "stores", ["store_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "ix_event_logs_store_id" in {index["name"] for index in sa.inspect(bind).get_indexes("event_logs")}:
        op.drop_index("ix_event_logs_store_id", table_name="event_logs")
    if bind.dialect.name != "sqlite" and "fk_event_logs_store_id" in {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("event_logs")}:
        op.drop_constraint("fk_event_logs_store_id", "event_logs", type_="foreignkey")
    op.drop_column("event_logs", "store_id")
