"""Add immutable correction links to customer profile records."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_profile_corrections"
down_revision: Union[str, None] = "20260825_tag_store_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("customer_profile_records")}
    if "correction_of_id" not in columns:
        op.add_column("customer_profile_records", sa.Column("correction_of_id", sa.Integer(), nullable=True))
    if "correction_reason" not in columns:
        op.add_column("customer_profile_records", sa.Column("correction_reason", sa.String(length=256), nullable=False, server_default=""))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("customer_profile_records")}
    if "ix_customer_profile_records_correction_of_id" not in indexes:
        op.create_index("ix_customer_profile_records_correction_of_id", "customer_profile_records", ["correction_of_id"])
    if bind.dialect.name != "sqlite":
        foreign_keys = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("customer_profile_records")}
        if "fk_profile_records_correction_of" not in foreign_keys:
            op.create_foreign_key("fk_profile_records_correction_of", "customer_profile_records", "customer_profile_records", ["correction_of_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite" and "fk_profile_records_correction_of" in {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("customer_profile_records")}:
        op.drop_constraint("fk_profile_records_correction_of", "customer_profile_records", type_="foreignkey")
    if "ix_customer_profile_records_correction_of_id" in {index["name"] for index in sa.inspect(bind).get_indexes("customer_profile_records")}:
        op.drop_index("ix_customer_profile_records_correction_of_id", table_name="customer_profile_records")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("customer_profile_records")}
    if "correction_reason" in columns:
        op.drop_column("customer_profile_records", "correction_reason")
    if "correction_of_id" in columns:
        op.drop_column("customer_profile_records", "correction_of_id")
