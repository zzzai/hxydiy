"""Add source and idempotency contract for technician profile quick notes."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260829_tech_profile_note"
down_revision: Union[str, Sequence[str], None] = "20260828_price_book_effective_to"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("customer_profile_records")}
    if "source" not in columns:
        op.add_column(
            "customer_profile_records",
            sa.Column("source", sa.String(length=32), nullable=False, server_default="service_observation"),
        )
    if "idempotency_key" not in columns:
        op.add_column(
            "customer_profile_records",
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        )
    indexes = {index["name"] for index in inspector.get_indexes("customer_profile_records")}
    if "uq_customer_profile_records_creator_idempotency" not in indexes:
        op.create_index(
            "uq_customer_profile_records_creator_idempotency",
            "customer_profile_records",
            ["store_id", "created_by_staff_id", "idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("customer_profile_records")}
    if "uq_customer_profile_records_creator_idempotency" in indexes:
        op.drop_index("uq_customer_profile_records_creator_idempotency", table_name="customer_profile_records")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("customer_profile_records")}
    if "idempotency_key" in columns:
        op.drop_column("customer_profile_records", "idempotency_key")
    if "source" in columns:
        op.drop_column("customer_profile_records", "source")
