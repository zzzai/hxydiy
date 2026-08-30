"""Add auditable quick customer profile records."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_profile_records"
down_revision: Union[str, None] = "20260825_audit_store_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "customer_profile_records" in inspector.get_table_names():
        return
    op.create_table(
        "customer_profile_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("selection_session_id", sa.String(), sa.ForeignKey("selection_sessions.id"), nullable=True),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("signals", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, column in (
        ("store_id", "store_id"),
        ("user_id", "user_id"),
        ("selection_session_id", "selection_session_id"),
        ("technician_id", "technician_id"),
        ("created_by_staff_id", "created_by_staff_id"),
        ("created_at", "created_at"),
    ):
        op.create_index(f"ix_customer_profile_records_{name}", "customer_profile_records", [column])


def downgrade() -> None:
    for name in ("created_at", "created_by_staff_id", "technician_id", "selection_session_id", "user_id", "store_id"):
        op.drop_index(f"ix_customer_profile_records_{name}", table_name="customer_profile_records")
    op.drop_table("customer_profile_records")
