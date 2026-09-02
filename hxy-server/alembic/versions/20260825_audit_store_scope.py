"""Add explicit store scope to audit logs and backfill legacy detail values."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_audit_store_scope"
down_revision: Union[str, None] = "20260825_event_store_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("audit_logs")}
    if "store_id" not in columns:
        op.add_column("audit_logs", sa.Column("store_id", sa.Integer(), nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("audit_logs")}
    if "ix_audit_logs_store_id" not in indexes:
        op.create_index("ix_audit_logs_store_id", "audit_logs", ["store_id"])
    if bind.dialect.name == "sqlite":
        op.execute(sa.text(
            "UPDATE audit_logs SET store_id = CAST(json_extract(detail, '$.store_id') AS INTEGER) "
            "WHERE store_id IS NULL AND json_extract(detail, '$.store_id') IS NOT NULL"
        ))
    elif bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "UPDATE audit_logs SET store_id = (detail->>'store_id')::integer "
            "WHERE store_id IS NULL AND detail->>'store_id' ~ '^[0-9]+$'"
        ))
    if bind.dialect.name != "sqlite":
        existing = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("audit_logs")}
        if "fk_audit_logs_store_id" not in existing:
            op.create_foreign_key("fk_audit_logs_store_id", "audit_logs", "stores", ["store_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite" and "fk_audit_logs_store_id" in {
        fk["name"] for fk in sa.inspect(bind).get_foreign_keys("audit_logs")
    }:
        op.drop_constraint("fk_audit_logs_store_id", "audit_logs", type_="foreignkey")
    if "ix_audit_logs_store_id" in {index["name"] for index in sa.inspect(bind).get_indexes("audit_logs")}:
        op.drop_index("ix_audit_logs_store_id", table_name="audit_logs")
    op.drop_column("audit_logs", "store_id")
