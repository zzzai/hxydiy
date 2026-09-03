"""Add membership origin store for admin data scoping."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_membership_store_scope"
down_revision: Union[str, None] = "20260821_sms_receipt_reconcile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "membership_store_id" not in columns:
        op.add_column("users", sa.Column("membership_store_id", sa.Integer(), nullable=True))
    if bind.dialect.name != "sqlite" and "membership_store_id" not in columns:
        op.create_foreign_key(
            "fk_users_membership_store_id",
            "users",
            "stores",
            ["membership_store_id"],
            ["id"],
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("users")}
    if "ix_users_membership_store_id" not in indexes:
        op.create_index("ix_users_membership_store_id", "users", ["membership_store_id"])

    # 为历史会员尽可能回填已发生业务的门店；无法从订单/选单推断的会员保持 NULL，
    # 由后台下一次开通或人工归属时补齐，避免把不确定归属伪造成事实。
    bind.execute(sa.text(
        """
        UPDATE users
        SET membership_store_id = (
            SELECT MIN(orders.store_id)
            FROM orders
            WHERE orders.user_id = users.id
              AND orders.store_id IS NOT NULL
        )
        WHERE users.is_member IS TRUE
          AND users.membership_store_id IS NULL
          AND EXISTS (
              SELECT 1 FROM orders
              WHERE orders.user_id = users.id
                AND orders.store_id IS NOT NULL
          )
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE users
        SET membership_store_id = (
            SELECT MIN(selection_sessions.store_id)
            FROM selection_sessions
            WHERE selection_sessions.customer_id = users.id
              AND selection_sessions.store_id IS NOT NULL
        )
        WHERE users.is_member IS TRUE
          AND users.membership_store_id IS NULL
          AND EXISTS (
              SELECT 1 FROM selection_sessions
              WHERE selection_sessions.customer_id = users.id
                AND selection_sessions.store_id IS NOT NULL
          )
        """
    ))


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_users_membership_store_id", table_name="users")
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_users_membership_store_id", "users", type_="foreignkey")
    op.drop_column("users", "membership_store_id")
