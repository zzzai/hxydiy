"""Add first-stage product catalog management fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260918_product_catalog_management"
down_revision: Union[str, None] = "20260910_membership_closure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("products")}
    if "member_price_cents" not in columns:
        op.add_column("products", sa.Column("member_price_cents", sa.Integer(), nullable=True))
    if "member_price_enabled" not in columns:
        op.add_column(
            "products",
            sa.Column("member_price_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "detail_modules" not in columns:
        op.add_column(
            "products",
            sa.Column("detail_modules", sa.JSON(), nullable=False, server_default="[]"),
        )
    if "display_order" not in columns:
        op.add_column(
            "products",
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        )

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("products")}
    if "ix_products_display_order" not in indexes:
        op.create_index("ix_products_display_order", "products", ["display_order"])


def downgrade() -> None:
    op.drop_index("ix_products_display_order", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("display_order")
        batch_op.drop_column("detail_modules")
        batch_op.drop_column("member_price_enabled")
        batch_op.drop_column("member_price_cents")
