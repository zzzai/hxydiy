"""Add source consumption history and balance snapshot tables (no production data).

Draft only: does not touch existing tables, does not import data. Production
execution requires separate review and user confirmation, plus pre-migration
backup and isolated restore rehearsal.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261114_member_consumption"
down_revision = "20261112_coupon_poster_links"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "membership_consumption_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("batch_key", sa.String(64), nullable=False),
        sa.Column("source_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("query_range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("last_page_complete", sa.Boolean(), nullable=True),
        sa.Column("coverage_gaps", sa.JSON(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="preview"),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "store_id", "batch_key", name="uq_member_consumption_batch"),
        sa.CheckConstraint("status IN ('preview', 'applied', 'blocked')", name="ck_member_consumption_batch_status"),
    )
    op.create_index("ix_membership_consumption_batches_store_id", "membership_consumption_batches", ["store_id"])

    op.create_table(
        "membership_consumption_bills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("membership_consumption_batches.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("source_bill_no", sa.String(128), nullable=False),
        sa.Column("source_bill_version", sa.String(64), nullable=True),
        sa.Column("bill_type", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("bill_status", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("source_version_no", sa.Integer(), nullable=True),
        sa.Column("source_current_marker", sa.String(32), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("store_price_total_cents", sa.BigInteger(), nullable=True),
        sa.Column("settled_total_cents", sa.BigInteger(), nullable=True),
        sa.Column("payment_evidence_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("price_plan_discount_cents", sa.BigInteger(), nullable=True),
        sa.Column("coupon_payment_cents", sa.BigInteger(), nullable=True),
        sa.Column("card_principal_debit_cents", sa.BigInteger(), nullable=True),
        sa.Column("card_bonus_debit_cents", sa.BigInteger(), nullable=True),
        sa.Column("cash_payment_cents", sa.BigInteger(), nullable=True),
        sa.Column("other_payment_cents", sa.BigInteger(), nullable=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("membership_cards.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("attribution_status", sa.String(24), nullable=False, server_default="unresolved"),
        sa.Column("refund_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("original_bill_id", sa.Integer(), sa.ForeignKey("membership_consumption_bills.id"), nullable=True),
        sa.Column("source_row_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("raw_evidence_ref", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "source", "store_id", "source_bill_no", "content_sha256",
            name="uq_member_consumption_bill_content",
        ),
        sa.CheckConstraint(
            "bill_type IN ('service', 'open_card', 'package', 'recharge', 'unknown')",
            name="ck_member_consumption_bill_type",
        ),
        sa.CheckConstraint(
            "bill_status IN ('normal_settled', 'voided', 'reversed', 'unknown')",
            name="ck_member_consumption_bill_status",
        ),
        sa.CheckConstraint(
            "attribution_status IN ('owned', 'shared', 'unresolved')",
            name="ck_member_consumption_attribution",
        ),
        sa.CheckConstraint(
            "refund_status IN ('none', 'partial', 'refunded', 'void', 'unknown')",
            name="ck_member_consumption_refund",
        ),
    )
    op.create_index("ix_membership_consumption_bills_batch_id", "membership_consumption_bills", ["batch_id"])
    op.create_index("ix_member_consumption_bill_user_store", "membership_consumption_bills", ["user_id", "store_id"])

    op.create_table(
        "membership_consumption_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_id", sa.Integer(), sa.ForeignKey("membership_consumption_bills.id"), nullable=False),
        sa.Column("source_line_key", sa.String(128), nullable=True),
        sa.Column("line_order", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("store_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("settled_cents", sa.BigInteger(), nullable=True),
        sa.Column("payment_breakdown_json", sa.JSON(), nullable=True),
        sa.Column("line_sha256", sa.String(64), nullable=False),
    )
    op.create_index("ix_member_consumption_line_bill", "membership_consumption_lines", ["bill_id"])

    op.create_table(
        "membership_balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("membership_cards.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal_cents", sa.BigInteger(), nullable=True),
        sa.Column("bonus_cents", sa.BigInteger(), nullable=True),
        sa.Column("total_cents", sa.BigInteger(), nullable=True),
        sa.Column("source_batch_id", sa.Integer(), sa.ForeignKey("membership_consumption_batches.id"), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("card_id", "observed_at", "source_batch_id", name="uq_member_balance_snapshot"),
    )
    op.create_index("ix_membership_balance_snapshots_card_id", "membership_balance_snapshots", ["card_id"])


def downgrade():
    bind = op.get_bind()
    tables = [
        "membership_balance_snapshots",
        "membership_consumption_lines",
        "membership_consumption_bills",
        "membership_consumption_batches",
    ]
    for table in tables:
        # On PostgreSQL, ACCESS EXCLUSIVE blocks concurrent writers so the
        # zero-row check cannot race with an insert before the table is dropped.
        if bind.dialect.name == "postgresql":
            bind.execute(sa.text(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"))
        count = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(f"{table} has rows; retain source records and use a forward rollback")
    op.drop_index("ix_membership_balance_snapshots_card_id", table_name="membership_balance_snapshots")
    op.drop_table("membership_balance_snapshots")
    op.drop_index("ix_member_consumption_line_bill", table_name="membership_consumption_lines")
    op.drop_table("membership_consumption_lines")
    op.drop_index("ix_member_consumption_bill_user_store", table_name="membership_consumption_bills")
    op.drop_index("ix_membership_consumption_bills_batch_id", table_name="membership_consumption_bills")
    op.drop_table("membership_consumption_bills")
    op.drop_index("ix_membership_consumption_batches_store_id", table_name="membership_consumption_batches")
    op.drop_table("membership_consumption_batches")
