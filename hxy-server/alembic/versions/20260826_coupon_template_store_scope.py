"""Scope coupon templates to stores."""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20260826_coupon_store_scope"
down_revision: Union[str, None] = "20260826_normalize_staff_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("coupon_templates")}
    if "store_id" not in columns:
        op.add_column("coupon_templates", sa.Column("store_id", sa.Integer(), nullable=True))
    indexes = {i["name"] for i in inspector.get_indexes("coupon_templates")}
    if "ix_coupon_templates_store_id" not in indexes:
        op.create_index("ix_coupon_templates_store_id", "coupon_templates", ["store_id"])
    # 无法从历史数据证明归属的券保持 NULL；应用层会拒绝在门店上下文外使用。
    if bind.dialect.name != "sqlite":
        fks = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("coupon_templates")}
        if "fk_coupon_templates_store_id" not in fks:
            op.create_foreign_key("fk_coupon_templates_store_id", "coupon_templates", "stores", ["store_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite" and "fk_coupon_templates_store_id" in {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("coupon_templates")}:
        op.drop_constraint("fk_coupon_templates_store_id", "coupon_templates", type_="foreignkey")
    if "ix_coupon_templates_store_id" in {i["name"] for i in sa.inspect(bind).get_indexes("coupon_templates")}:
        op.drop_index("ix_coupon_templates_store_id", table_name="coupon_templates")
    op.drop_column("coupon_templates", "store_id")
