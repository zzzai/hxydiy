"""Add store-scoped media assets."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20260830_media_assets"
down_revision: Union[str, Sequence[str], None] = "20260829_tech_profile_note"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("object_key", sa.String(length=256), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False, server_default="image"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("object_key", name="uq_media_assets_object_key"),
    )
    op.create_index("ix_media_assets_store_id", "media_assets", ["store_id"])
    op.create_index("ix_media_assets_deleted_at", "media_assets", ["deleted_at"])

def downgrade() -> None:
    op.drop_index("ix_media_assets_deleted_at", table_name="media_assets")
    op.drop_index("ix_media_assets_store_id", table_name="media_assets")
    op.drop_table("media_assets")
