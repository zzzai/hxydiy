"""Allow standalone store feedback without inventing a service position."""

from alembic import op
import sqlalchemy as sa


revision = "20261023_store_feedback"
down_revision = "20261025_exception_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("visit_feedback") as batch:
        batch.alter_column("room_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM visit_feedback WHERE room_id IS NULL"
    )).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade while roomless visit feedback exists; preserve these records")
    with op.batch_alter_table("visit_feedback") as batch:
        batch.alter_column("room_id", existing_type=sa.Integer(), nullable=False)
