"""Add account role and scope assignments."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260921_staff_scope"
down_revision: Union[str, None] = "20260921_visit_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_scope_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('brand_admin', 'hq_operator', 'store_manager', 'store_staff')", name="ck_staff_scope_assignment_role"),
        sa.CheckConstraint("scope_type IN ('brand', 'store')", name="ck_staff_scope_assignment_scope_type"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_staff_scope_assignment_status"),
        sa.CheckConstraint(
            "(scope_type = 'brand' AND scope_id IS NULL AND role IN ('brand_admin', 'hq_operator')) OR "
            "(scope_type = 'store' AND scope_id IS NOT NULL AND role IN ('store_manager', 'store_staff'))",
            name="ck_staff_scope_assignment_role_scope",
        ),
    )
    op.create_index("ix_staff_scope_assignments_staff_id", "staff_scope_assignments", ["staff_id"])
    op.create_index("ix_staff_scope_assignments_role", "staff_scope_assignments", ["role"])
    op.create_index("ix_staff_scope_assignments_scope_type", "staff_scope_assignments", ["scope_type"])
    op.create_index("ix_staff_scope_assignments_scope_id", "staff_scope_assignments", ["scope_id"])
    op.create_index("ix_staff_scope_assignments_status", "staff_scope_assignments", ["status"])
    op.create_index(
        "uq_staff_scope_assignment_active_brand",
        "staff_scope_assignments",
        ["staff_id", "role"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'brand' AND status = 'active'"),
        sqlite_where=sa.text("scope_type = 'brand' AND status = 'active'"),
    )
    op.create_index(
        "uq_staff_scope_assignment_active_store",
        "staff_scope_assignments",
        ["staff_id", "role", "scope_id"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'store' AND status = 'active'"),
        sqlite_where=sa.text("scope_type = 'store' AND status = 'active'"),
    )

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("assignment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("actor_role", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("scope_type", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("scope_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_audit_logs_assignment_id", "staff_scope_assignments", ["assignment_id"], ["id"])
        batch_op.create_foreign_key("fk_audit_logs_scope_id", "stores", ["scope_id"], ["id"])
    op.create_index("ix_audit_logs_assignment_id", "audit_logs", ["assignment_id"])

    bind = op.get_bind()
    staff_columns = {column["name"] for column in sa.inspect(bind).get_columns("staff")}
    required_staff_columns = {
        "id", "username", "role", "store_id", "technician_id", "status", "credentials_version",
    }
    # Some historical migration tests intentionally reconstruct only the columns needed by
    # their older revision. The new table/audit columns must still migrate, but there is no
    # trustworthy account snapshot to backfill from when compatibility fields are absent.
    if not required_staff_columns.issubset(staff_columns):
        return
    rows = bind.execute(sa.text(
        "SELECT id, username, role, store_id, technician_id, status, credentials_version FROM staff ORDER BY id"
    )).mappings()
    for row in rows:
        if row["technician_id"] is not None or row["role"] == "technician":
            continue
        assignment_role = None
        scope_type = None
        scope_id = None
        if row["username"] == "admin":
            assignment_role, scope_type = "brand_admin", "brand"
            bind.execute(sa.text(
                "UPDATE staff SET role = 'admin', store_id = NULL, credentials_version = credentials_version + 1 WHERE id = :staff_id"
            ), {"staff_id": row["id"]})
        elif row["role"] == "admin" and row["store_id"] is None:
            assignment_role, scope_type = "brand_admin", "brand"
        elif row["role"] in {"admin", "manager"} and row["store_id"] is not None:
            assignment_role, scope_type, scope_id = "store_manager", "store", row["store_id"]
        elif row["role"] == "staff" and row["store_id"] is not None:
            assignment_role, scope_type, scope_id = "store_staff", "store", row["store_id"]
        if assignment_role is None:
            continue
        bind.execute(sa.text("""
            INSERT INTO staff_scope_assignments (staff_id, role, scope_type, scope_id, status)
            VALUES (:staff_id, :role, :scope_type, :scope_id, :status)
        """), {
            "staff_id": row["id"],
            "role": assignment_role,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "status": "active" if row["status"] == "active" else "disabled",
        })


def downgrade() -> None:
    op.drop_index("ix_audit_logs_assignment_id", table_name="audit_logs")
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("fk_audit_logs_scope_id", type_="foreignkey")
        batch_op.drop_constraint("fk_audit_logs_assignment_id", type_="foreignkey")
        batch_op.drop_column("scope_id")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("actor_role")
        batch_op.drop_column("assignment_id")
    op.drop_table("staff_scope_assignments")
