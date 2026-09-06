"""Add current wellness-profile projection and consent storage."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260906_wellness_current"
down_revision: Union[str, None] = "20260905_tech_history_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_profile_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=256), nullable=False),
        sa.Column("data_categories_json", sa.JSON(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("consent_method", sa.String(length=32), nullable=False),
        sa.Column("consent_text_version", sa.String(length=64), nullable=False),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.create_index("ix_customer_profile_consents_customer_id", "customer_profile_consents", ["customer_id"])
    op.create_index("ix_customer_profile_consents_consent_type", "customer_profile_consents", ["consent_type"])
    op.create_index("ix_customer_profile_consents_selection_session_id", "customer_profile_consents", ["selection_session_id"])
    op.create_index("ix_customer_profile_consents_status", "customer_profile_consents", ["status"])

    op.create_table(
        "customer_profile_current",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("profile_value_key", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("profile_value_json", sa.JSON(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("body_side", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("source_record_id", sa.Integer(), sa.ForeignKey("customer_profile_records.id"), nullable=False),
        sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensitivity_level", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("consent_id", sa.Integer(), sa.ForeignKey("customer_profile_consents.id"), nullable=True),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "customer_id", "profile_code", "profile_value_key", "body_area_code", "body_side",
            name="uq_customer_profile_current_dimension",
        ),
    )
    op.create_index("ix_customer_profile_current_customer_id", "customer_profile_current", ["customer_id"])
    op.create_index("ix_customer_profile_current_source_record_id", "customer_profile_current", ["source_record_id"])
    op.create_index("ix_customer_profile_current_valid_until", "customer_profile_current", ["valid_until"])
    op.create_index("ix_customer_profile_current_status", "customer_profile_current", ["status"])
    op.create_index("ix_customer_profile_current_customer_valid", "customer_profile_current", ["customer_id", "status", "valid_until"])


def downgrade() -> None:
    op.drop_index("ix_customer_profile_current_customer_valid", table_name="customer_profile_current")
    op.drop_index("ix_customer_profile_current_status", table_name="customer_profile_current")
    op.drop_index("ix_customer_profile_current_valid_until", table_name="customer_profile_current")
    op.drop_index("ix_customer_profile_current_source_record_id", table_name="customer_profile_current")
    op.drop_index("ix_customer_profile_current_customer_id", table_name="customer_profile_current")
    op.drop_table("customer_profile_current")
    op.drop_index("ix_customer_profile_consents_status", table_name="customer_profile_consents")
    op.drop_index("ix_customer_profile_consents_selection_session_id", table_name="customer_profile_consents")
    op.drop_index("ix_customer_profile_consents_consent_type", table_name="customer_profile_consents")
    op.drop_index("ix_customer_profile_consents_customer_id", table_name="customer_profile_consents")
    op.drop_table("customer_profile_consents")
