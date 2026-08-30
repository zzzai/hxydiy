"""Add store-scoped editable DIY page content."""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20260810_page_contents"
down_revision: Union[str, None] = "20260810_diy_content_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "page_contents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("page_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False, server_default="到店选项目"),
        sa.Column("subtitle", sa.String(length=256), nullable=False, server_default="按需要，自由搭配"),
        sa.Column("promo_banners", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tea_options", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("coupon_prompt", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("brand_story", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "page_key", name="uq_page_contents_store_key"),
    )
    op.create_index("ix_page_contents_store_id", "page_contents", ["store_id"])
    op.create_index("ix_page_contents_page_key", "page_contents", ["page_key"])
    op.create_index("ix_page_contents_published", "page_contents", ["published"])


def downgrade() -> None:
    op.drop_index("ix_page_contents_published", table_name="page_contents")
    op.drop_index("ix_page_contents_page_key", table_name="page_contents")
    op.drop_index("ix_page_contents_store_id", table_name="page_contents")
    op.drop_table("page_contents")
