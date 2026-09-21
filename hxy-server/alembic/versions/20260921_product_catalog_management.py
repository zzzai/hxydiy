"""Add product catalog management fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260921_product_catalog"
down_revision: Union[str, None] = "20260910_membership_closure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "products" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("products")}
    if "member_price_cents" not in existing_columns:
        op.add_column("products", sa.Column("member_price_cents", sa.Integer(), nullable=True))
    if "detail_modules" not in existing_columns:
        op.add_column("products", sa.Column("detail_modules", sa.JSON(), nullable=False, server_default="[]"))
    if "display_order" not in existing_columns:
        op.add_column("products", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))

    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("products")}
    if "ix_products_display_order" not in existing_indexes:
        op.create_index("ix_products_display_order", "products", ["display_order"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "products" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("products")}
    if "ix_products_display_order" in existing_indexes:
        op.drop_index("ix_products_display_order", table_name="products")
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("products")}
    for column_name in ("display_order", "detail_modules", "member_price_cents"):
        if column_name in existing_columns:
            op.drop_column("products", column_name)
