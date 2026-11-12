"""Add single-claim poster links without changing existing coupons."""

from alembic import op
import sqlalchemy as sa

revision = "20261112_coupon_poster_links"
down_revision = "20261109_daily_manager_ops"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coupon_poster_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("coupon_templates.id"), nullable=False),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("coupon_id", sa.Integer(), sa.ForeignKey("user_coupons.id"), nullable=True, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("created_by_staff_id", "request_id", name="uq_coupon_poster_request"),
    )
    op.create_index("ix_coupon_poster_links_store_id", "coupon_poster_links", ["store_id"])


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM coupon_poster_links")).scalar_one()
    if count:
        raise RuntimeError("Poster links exist; retain issued rights and use a forward rollback")
    op.drop_index("ix_coupon_poster_links_store_id", table_name="coupon_poster_links")
    op.drop_table("coupon_poster_links")
