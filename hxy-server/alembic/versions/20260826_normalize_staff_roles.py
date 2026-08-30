"""Normalize legacy staff roles and enforce technician account binding."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_normalize_staff_roles"
down_revision: Union[str, None] = "20260826_technician_portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def normalize_roles(bind) -> None:
    """Migrate legacy role values without touching audit JSON snapshots.

    ``staff`` rows are only valid technician identities when explicitly bound;
    aborting before updates leaves the transaction safe to roll back.
    """
    orphaned = bind.execute(
        sa.text("SELECT username FROM staff WHERE role = 'staff' AND technician_id IS NULL")
    ).scalars().all()
    if orphaned:
        names = ", ".join(str(item) for item in orphaned)
        raise RuntimeError(f"发现未绑定技师的 staff 账号: {names}")
    bind.execute(sa.text("UPDATE staff SET role = 'manager' WHERE role = 'admin'"))
    bind.execute(sa.text("UPDATE staff SET role = 'technician' WHERE role = 'staff'"))


def upgrade() -> None:
    bind = op.get_bind()
    normalize_roles(bind)
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("staff")}
    constraints = {c.get("name") for c in inspector.get_unique_constraints("staff")}
    if "ix_staff_technician_id" not in indexes and "uq_staff_technician_id" not in constraints:
        op.create_index("ix_staff_technician_id", "staff", ["technician_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE staff SET role = 'admin' WHERE role = 'manager'"))
    bind.execute(sa.text("UPDATE staff SET role = 'staff' WHERE role = 'technician'"))
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("staff")}
    if "ix_staff_technician_id" in indexes:
        op.drop_index("ix_staff_technician_id", table_name="staff")
