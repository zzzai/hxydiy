"""Add independent source-card entitlements without backfilling guessed rights."""

from alembic import op
import sqlalchemy as sa

revision = "20260928_membership_cards"
down_revision = "20260924_aux_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membership_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_card_key", sa.String(64), nullable=False),
        sa.Column("card_type", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("balance_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_card_key", name="uq_membership_card_source"),
        sa.CheckConstraint("card_type IN ('annual', 'stored')", name="ck_membership_card_type"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_membership_card_status"),
        sa.CheckConstraint("balance_cents >= 0", name="ck_membership_card_balance"),
        sa.CheckConstraint("card_type <> 'annual' OR expires_at IS NOT NULL", name="ck_membership_card_annual_expiry"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > started_at", name="ck_membership_card_dates"),
    )
    op.create_index("ix_membership_cards_user_id", "membership_cards", ["user_id"])
    op.create_index("ix_membership_cards_store_id", "membership_cards", ["store_id"])


def downgrade() -> None:
    op.drop_table("membership_cards")
