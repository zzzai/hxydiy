"""Add isolated WeCom staff identities, OAuth attempts and tag contributions."""

from alembic import op
import sqlalchemy as sa

revision = "20261017_wecom_technician"
down_revision = "20260928_membership_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_external_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("corp_id", sa.String(128), nullable=False),
        sa.Column("userid", sa.String(128), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("binding_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provider_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "corp_id", "userid", name="uq_staff_external_identity_subject"),
        sa.CheckConstraint("userid = lower(userid)", name="ck_staff_external_identity_userid_canonical"),
        sa.CheckConstraint("binding_version >= 1", name="ck_staff_external_identity_version"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_staff_external_identity_status"),
    )
    op.create_index("ix_staff_external_identities_staff_id", "staff_external_identities", ["staff_id"])
    op.create_index("uq_staff_external_identity_active_staff", "staff_external_identities", ["provider", "staff_id"],
                    unique=True, postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_table(
        "staff_oauth_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("identity_id", sa.Integer(), sa.ForeignKey("staff_external_identities.id"), nullable=True),
        sa.Column("binding_version", sa.Integer(), nullable=True),
        sa.Column("credentials_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'processing', 'ready', 'used', 'failed')", name="ck_staff_oauth_attempt_status"),
    )
    op.create_index("ix_staff_oauth_attempts_expires_at", "staff_oauth_attempts", ["expires_at"])
    op.create_table(
        "customer_tag_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("customer_tags.id"), nullable=False),
        sa.Column("created_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("selection_session_id", sa.String(36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("occupancy_id", sa.Integer(), sa.ForeignKey("position_occupancies.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("revoke_reason", sa.String(256), server_default="", nullable=False),
        sa.UniqueConstraint("store_id", "created_by_staff_id", "idempotency_key", name="uq_customer_tag_contribution_creator_key"),
    )
    for column in ("store_id", "user_id", "tag_id", "created_by_staff_id", "technician_id", "selection_session_id", "occupancy_id"):
        op.create_index(f"ix_customer_tag_contributions_{column}", "customer_tag_contributions", [column])
    op.create_index("uq_customer_tag_contribution_active_context", "customer_tag_contributions",
                    ["user_id", "tag_id", "created_by_staff_id", "occupancy_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL"), sqlite_where=sa.text("revoked_at IS NULL"))


def downgrade() -> None:
    op.drop_table("customer_tag_contributions")
    op.drop_table("staff_oauth_attempts")
    op.drop_table("staff_external_identities")
