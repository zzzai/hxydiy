"""Add versioned project catalogs, mixed options, and option prices."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_catalog_options"
down_revision: Union[str, None] = "20260814_settlement_p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_catalog_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.UniqueConstraint("project_id", "version", name="uq_project_catalog_version"),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_project_catalog_version_project_id_id",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_project_catalog_version_status",
        ),
    )
    op.create_index(
        "ix_project_catalog_versions_project_id",
        "project_catalog_versions",
        ["project_id"],
    )
    op.create_index(
        "ix_project_catalog_versions_status",
        "project_catalog_versions",
        ["status"],
    )
    op.create_index(
        "uq_project_catalog_one_draft",
        "project_catalog_versions",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status = 'draft'"),
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_project_catalog_one_published",
        "project_catalog_versions",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status = 'published'"),
        postgresql_where=sa.text("status = 'published'"),
    )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("current_published_version_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_projects_current_published_version_id",
            "project_catalog_versions",
            ["id", "current_published_version_id"],
            ["project_id", "id"],
        )

    op.create_table(
        "project_option_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "catalog_version_id",
            sa.Integer(),
            sa.ForeignKey("project_catalog_versions.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("selection_mode", sa.String(length=16), nullable=False, server_default="single"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_select", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_select", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "catalog_version_id",
            "code",
            name="uq_project_option_group_code",
        ),
        sa.CheckConstraint(
            "selection_mode IN ('single', 'multiple')",
            name="ck_project_option_group_selection_mode",
        ),
    )
    op.create_index(
        "ix_project_option_groups_catalog_version_id",
        "project_option_groups",
        ["catalog_version_id"],
    )

    op.create_table(
        "project_option_choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "option_group_id",
            sa.Integer(),
            sa.ForeignKey("project_option_groups.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("choice_type", sa.String(length=24), nullable=False),
        sa.Column("linked_project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "pinned_linked_catalog_version_id",
            sa.Integer(),
            sa.ForeignKey("project_catalog_versions.id"),
            nullable=True,
        ),
        sa.Column("charge_mode", sa.String(length=24), nullable=False),
        sa.Column("independently_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("coupon_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("annual_gift_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "qualifies_for_foot_bath_bundle",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.UniqueConstraint("option_group_id", "code", name="uq_project_option_choice_code"),
        sa.CheckConstraint(
            "choice_type IN ('preference', 'linked_project', 'dedicated_charge')",
            name="ck_project_option_choice_type",
        ),
        sa.CheckConstraint(
            "charge_mode IN ('free', 'inherit_linked_price', 'custom_price')",
            name="ck_project_option_choice_charge_mode",
        ),
    )
    op.create_index(
        "ix_project_option_choices_option_group_id",
        "project_option_choices",
        ["option_group_id"],
    )
    op.create_index(
        "ix_project_option_choices_linked_project_id",
        "project_option_choices",
        ["linked_project_id"],
    )
    op.create_index(
        "ix_project_option_choices_pinned_linked_catalog_version_id",
        "project_option_choices",
        ["pinned_linked_catalog_version_id"],
    )
    op.create_index(
        "ix_project_option_choices_status",
        "project_option_choices",
        ["status"],
    )

    op.create_table(
        "option_choice_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "option_choice_id",
            sa.Integer(),
            sa.ForeignKey("project_option_choices.id"),
            nullable=False,
        ),
        sa.Column("price_type", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "option_choice_id",
            "price_type",
            "effective_from",
            name="uq_option_choice_price_effective",
        ),
        sa.CheckConstraint(
            "price_type IN ('store', 'group', 'member')",
            name="ck_option_choice_price_type",
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_option_choice_price_non_negative"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_option_choice_price_valid_interval",
        ),
    )
    op.create_index(
        "ix_option_choice_prices_option_choice_id",
        "option_choice_prices",
        ["option_choice_id"],
    )
    op.create_index(
        "ix_option_choice_prices_price_type",
        "option_choice_prices",
        ["price_type"],
    )
    with op.batch_alter_table("price_book") as batch_op:
        batch_op.create_check_constraint(
            "ck_price_book_amount_non_negative",
            "amount_cents >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("price_book") as batch_op:
        batch_op.drop_constraint("ck_price_book_amount_non_negative", type_="check")
    op.drop_table("option_choice_prices")
    op.drop_table("project_option_choices")
    op.drop_table("project_option_groups")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("fk_projects_current_published_version_id", type_="foreignkey")
        batch_op.drop_column("current_published_version_id")
    op.drop_table("project_catalog_versions")
