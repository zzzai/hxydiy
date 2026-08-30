"""Add technician credential version and invite purpose."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_tech_acct_lifecycle"
down_revision: Union[str, tuple[str, str], None] = (
    "20260825_staff_expiry",
    "20260826_coupon_store_scope",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    staff_columns = {column["name"] for column in inspector.get_columns("staff")}
    if "credentials_version" not in staff_columns:
        op.add_column(
            "staff",
            sa.Column("credentials_version", sa.Integer(), nullable=False, server_default="1"),
        )

    invite_columns = {column["name"] for column in inspector.get_columns("technician_invites")}
    if "purpose" not in invite_columns:
        op.add_column(
            "technician_invites",
            sa.Column("purpose", sa.String(length=16), nullable=False, server_default="activate"),
        )
    if bind.dialect.name != "sqlite":
        constraints = {
            constraint.get("name")
            for constraint in sa.inspect(bind).get_check_constraints("technician_invites")
        }
        if "ck_technician_invite_purpose" not in constraints:
            op.create_check_constraint(
                "ck_technician_invite_purpose",
                "technician_invites",
                "purpose IN ('activate', 'reset')",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        constraints = {
            constraint.get("name")
            for constraint in sa.inspect(bind).get_check_constraints("technician_invites")
        }
        if "ck_technician_invite_purpose" in constraints:
            op.drop_constraint("ck_technician_invite_purpose", "technician_invites", type_="check")
    inspector = sa.inspect(bind)
    invite_columns = {column["name"] for column in inspector.get_columns("technician_invites")}
    if "purpose" in invite_columns:
        op.drop_column("technician_invites", "purpose")
    staff_columns = {column["name"] for column in inspector.get_columns("staff")}
    if "credentials_version" in staff_columns:
        op.drop_column("staff", "credentials_version")
