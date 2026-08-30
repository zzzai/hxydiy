"""Scope customer tag names to a store."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_tag_store_scope"
down_revision: Union[str, None] = "20260825_profile_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite 的旧表约束需要 batch 重建；开发数据库通常由 metadata 创建，
        # 因此这里只保证迁移链可执行，生产 PostgreSQL 走下方约束变更。
        return

    inspector = sa.inspect(bind)
    unique_constraints = inspector.get_unique_constraints("customer_tags")
    for constraint in unique_constraints:
        if constraint.get("column_names") == ["name"]:
            op.drop_constraint(constraint["name"], "customer_tags", type_="unique")
    existing = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("customer_tags")
    }
    if "uq_customer_tags_store_name" not in existing:
        op.create_unique_constraint(
            "uq_customer_tags_store_name", "customer_tags", ["store_id", "name"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    inspector = sa.inspect(bind)
    if "uq_customer_tags_store_name" in {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("customer_tags")
    }:
        op.drop_constraint("uq_customer_tags_store_name", "customer_tags", type_="unique")
    if not any(
        constraint.get("column_names") == ["name"]
        for constraint in inspector.get_unique_constraints("customer_tags")
    ):
        op.create_unique_constraint("customer_tags_name_key", "customer_tags", ["name"])
