"""membership trusted device and dynamic code

Revision ID: 20260905_membership_verification
Revises: 20260905_customer_single_session
"""
from alembic import op
import sqlalchemy as sa

revision = "20260905_membership_verification"
down_revision = "20260905_customer_single_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("selection_sessions") as batch:
        batch.add_column(sa.Column("membership_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("membership_verified_by_staff_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_selection_membership_verifier", "staff", ["membership_verified_by_staff_id"], ["id"])
    op.create_table("customer_trusted_devices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("status", sa.String(16), nullable=False, server_default="active"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("last_seen_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_customer_trusted_devices_user_id", "customer_trusted_devices", ["user_id"])
    op.create_index("uq_customer_active_trusted_device", "customer_trusted_devices", ["user_id"], unique=True, postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_table("membership_codes", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("trusted_device_id", sa.Integer(), sa.ForeignKey("customer_trusted_devices.id"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("status", sa.String(24), nullable=False, server_default="issued"), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("scanned_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id")), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id")), sa.Column("selection_session_id", sa.String(36), sa.ForeignKey("selection_sessions.id")), sa.Column("idempotency_key", sa.String(96), unique=True), sa.Column("scanned_at", sa.DateTime(timezone=True)), sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_membership_codes_user_id", "membership_codes", ["user_id"])
    op.create_index("ix_membership_codes_token_hash", "membership_codes", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("membership_codes")
    op.drop_table("customer_trusted_devices")
    with op.batch_alter_table("selection_sessions") as batch:
        batch.drop_constraint("fk_selection_membership_verifier", type_="foreignkey")
        batch.drop_column("membership_verified_by_staff_id")
        batch.drop_column("membership_verified_at")
