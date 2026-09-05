"""Add versioned service-reference metadata and read indexes."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_service_reference_v2"
down_revision = "20260830_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer_profile_records",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "customer_profile_records",
        sa.Column("taxonomy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "customer_profile_records",
        sa.Column("customer_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "customer_profile_records",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_customer_profile_store_user_confirmed_created",
        "customer_profile_records",
        ["store_id", "user_id", "customer_confirmed", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_customer_profile_store_technician_created",
        "customer_profile_records",
        ["store_id", "technician_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_profile_store_technician_created", table_name="customer_profile_records")
    op.drop_index("ix_customer_profile_store_user_confirmed_created", table_name="customer_profile_records")
    op.drop_column("customer_profile_records", "confirmed_at")
    op.drop_column("customer_profile_records", "customer_confirmed")
    op.drop_column("customer_profile_records", "taxonomy_version")
    op.drop_column("customer_profile_records", "schema_version")
