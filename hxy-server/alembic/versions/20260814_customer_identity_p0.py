"""Add customer identity constraints and external identity mappings."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260814_customer_identity_p0"
down_revision: Union[str, None] = "20260812_selection_closure_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        """
        SELECT phone, COUNT(*) AS customer_count
        FROM users
        WHERE phone <> ''
        GROUP BY phone
        HAVING COUNT(*) > 1
        LIMIT 20
        """
    )).all()
    if duplicates:
        phones = ", ".join(str(row.phone) for row in duplicates)
        raise RuntimeError(
            f"duplicate customer phones must be resolved before migration: {phones}"
        )

    op.create_index(
        "uq_users_phone_nonempty",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone <> ''"),
        sqlite_where=sa.text("phone <> ''"),
    )
    op.create_table(
        "customer_external_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_subject_id", sa.String(length=128), nullable=False),
        sa.Column("external_member_no", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider",
            "external_subject_id",
            name="uq_customer_external_identity_subject",
        ),
    )
    op.create_index(
        "ix_customer_external_identities_customer_id",
        "customer_external_identities",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_external_identities_provider",
        "customer_external_identities",
        ["provider"],
    )
    op.create_index(
        "ix_customer_external_identities_status",
        "customer_external_identities",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_external_identities_status", table_name="customer_external_identities")
    op.drop_index("ix_customer_external_identities_provider", table_name="customer_external_identities")
    op.drop_index("ix_customer_external_identities_customer_id", table_name="customer_external_identities")
    op.drop_table("customer_external_identities")
    op.drop_index("uq_users_phone_nonempty", table_name="users")
