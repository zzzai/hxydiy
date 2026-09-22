"""Add brand project templates, price policies, and store price overrides.

MULTI-STORE-005 PR1: brand-level catalog templates with three-layer pricing
(standard price / override rules / forced price), backfilling existing store
projects into templates without changing any published price or reference.
Also lands the member-price toggle (catalog-closure backlog) on projects and
products, mirroring the existing addons.member_price_enabled semantics.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260922_project_templates"
down_revision: Union[str, None] = "20260921_staff_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column("desc", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("detail_modules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("brand_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_project_templates_code"),
    )
    op.create_index("ix_project_templates_code", "project_templates", ["code"], unique=True)
    op.create_index("ix_project_templates_category", "project_templates", ["category"])
    op.create_index("ix_project_templates_display_order", "project_templates", ["display_order"])

    op.create_table(
        "template_price_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("project_templates.id"), nullable=False),
        sa.Column("price_type", sa.String(length=16), nullable=False),
        sa.Column("standard_price_cents", sa.Integer(), nullable=False),
        sa.Column("override_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_price_cents", sa.Integer(), nullable=True),
        sa.Column("max_price_cents", sa.Integer(), nullable=True),
        sa.Column("force_standard", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price_type IN ('store', 'member', 'group')", name="ck_template_price_policies_type"),
        sa.CheckConstraint("standard_price_cents >= 0", name="ck_template_price_policies_standard_non_negative"),
        sa.UniqueConstraint("template_id", "price_type", name="uq_template_price_policies_template_type"),
    )
    op.create_index("ix_template_price_policies_template_id", "template_price_policies", ["template_id"])
    op.create_index("ix_template_price_policies_price_type", "template_price_policies", ["price_type"])

    op.create_table(
        "store_price_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("price_type", sa.String(length=16), nullable=False),
        sa.Column("override_price_cents", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price_type IN ('store', 'member', 'group')", name="ck_store_price_overrides_type"),
        sa.CheckConstraint("override_price_cents >= 0", name="ck_store_price_overrides_non_negative"),
        sa.UniqueConstraint("project_id", "price_type", name="uq_store_price_overrides_project_type"),
    )
    op.create_index("ix_store_price_overrides_project_id", "store_price_overrides", ["project_id"])

    # Plain ADD COLUMN instead of batch_alter_table: alembic's batch column
    # reordering cannot handle the pre-existing projects <-> project_catalog_versions
    # circular FK (20260815). FK is created on PostgreSQL only; SQLite cannot
    # ALTER in constraints and gets the FK from model metadata create_all.
    #
    # Table-existence guards follow the 20260921_staff_scope precedent: some
    # historical migration tests intentionally reconstruct only the tables their
    # older revision needs; projects/products/price_book may be absent there.
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "projects" in existing_tables:
        op.add_column("projects", sa.Column("template_id", sa.Integer(), nullable=True))
        op.add_column(
            "projects",
            sa.Column("member_price_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_projects_template_id", "projects", ["template_id"])
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_projects_template_id", "projects", "project_templates", ["template_id"], ["id"]
            )

    if "products" in existing_tables:
        op.add_column(
            "products",
            sa.Column("member_price_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if "projects" not in existing_tables:
        return

    # Backfill: each existing store project becomes a brand template. Set-based
    # INSERT...SELECT keeps JSON columns database-native (dialect-safe for both
    # SQLite and PostgreSQL). Prices are snapshotted from the currently
    # effective price_book rows so every store's effective price resolves to
    # exactly what it was before the migration.
    bind.execute(sa.text("""
        INSERT INTO project_templates
        (code, name, category, duration_min, desc, image_url, detail_modules, tags,
         display_order, brand_enabled, created_by)
        SELECT code, name, category, duration_min,
               COALESCE(summary, ''), COALESCE(image_url, ''),
               COALESCE(detail_modules, CAST('[]' AS JSON)),
               COALESCE(tags, CAST('[]' AS JSON)),
               display_order, true, 'system'
        FROM projects ORDER BY id
    """))
    bind.execute(sa.text("""
        UPDATE projects SET template_id = (
            SELECT id FROM project_templates WHERE project_templates.code = projects.code
        )
    """))
    if "price_book" not in existing_tables:
        return

    bind.execute(sa.text("""
        INSERT INTO template_price_policies
        (template_id, price_type, standard_price_cents, override_allowed,
         min_price_cents, max_price_cents, force_standard)
        SELECT p.template_id, pb.price_type, pb.amount_cents, true, NULL, NULL, false
        FROM price_book pb
        JOIN projects p ON p.id = pb.project_id
        WHERE pb.effective_to IS NULL
          AND pb.price_type IN ('store', 'member', 'group')
          AND p.template_id IS NOT NULL
          AND pb.id = (
              SELECT MAX(pb2.id) FROM price_book pb2
              WHERE pb2.project_id = pb.project_id
                AND pb2.price_type = pb.price_type
                AND pb2.effective_to IS NULL
          )
    """))


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "products" in existing_tables:
        op.drop_column("products", "member_price_enabled")
    if "projects" in existing_tables:
        if op.get_bind().dialect.name != "sqlite":
            op.drop_constraint("fk_projects_template_id", "projects", type_="foreignkey")
        op.drop_index("ix_projects_template_id", table_name="projects")
        op.drop_column("projects", "member_price_enabled")
        op.drop_column("projects", "template_id")
    op.drop_table("store_price_overrides")
    op.drop_table("template_price_policies")
    op.drop_table("project_templates")
