"""Add immutable selection revisions and service-time change requests.

This revision is additive. Do not run downgrade in production while V2 records
exist; restore the verified backup instead.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_selection_closure_v2"
down_revision: Union[str, None] = "20260812_diy_counter_checkout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("addons") as batch:
        batch.add_column(sa.Column("parent_project_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_addons_parent_project_id_projects",
            "projects",
            ["parent_project_id"],
            ["id"],
        )
        batch.add_column(sa.Column("store_price_cents", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("member_price_cents", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("member_price_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("independently_sellable", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("can_attach_to_parent", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("summary", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("image_url", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("chargeable", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_index("ix_addons_parent_project_id", ["parent_project_id"])
        batch.create_index("ix_addons_display_order", ["display_order"])
    op.create_table(
        "selection_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="submitted"),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.UniqueConstraint("selection_session_id", "revision_no", name="uq_selection_revision_no"),
        sa.UniqueConstraint("selection_session_id", "idempotency_key", name="uq_selection_revision_idempotency"),
    )
    op.create_index("ix_selection_revisions_selection_session_id", "selection_revisions", ["selection_session_id"])
    op.create_index("ix_selection_revisions_state", "selection_revisions", ["state"])
    op.create_table(
        "selection_change_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("selection_revision_id", sa.String(length=36), sa.ForeignKey("selection_revisions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="awaiting_staff_confirmation"),
        sa.Column("reason", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
    )
    op.create_index("ix_selection_change_requests_selection_session_id", "selection_change_requests", ["selection_session_id"])
    op.create_index("ix_selection_change_requests_selection_revision_id", "selection_change_requests", ["selection_revision_id"])
    op.create_index("ix_selection_change_requests_state", "selection_change_requests", ["state"])
    op.create_table(
        "service_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("selection_session_id", sa.String(length=36), sa.ForeignKey("selection_sessions.id"), nullable=False),
        sa.Column("selection_revision_id", sa.String(length=36), sa.ForeignKey("selection_revisions.id"), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_service_lines_selection_session_id", "service_lines", ["selection_session_id"])
    op.create_index("ix_service_lines_selection_revision_id", "service_lines", ["selection_revision_id"])
    op.create_index("ix_service_lines_state", "service_lines", ["state"])


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("selection_revisions", "selection_change_requests", "service_lines"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).first():
            raise RuntimeError(
                "selection closure V2 records exist; production downgrade is blocked. Restore the verified backup instead."
            )
    with op.batch_alter_table("addons") as batch:
        batch.drop_index("ix_addons_parent_project_id")
        batch.drop_index("ix_addons_display_order")
        batch.drop_constraint("fk_addons_parent_project_id_projects", type_="foreignkey")
        batch.drop_column("chargeable")
        batch.drop_column("display_order")
        batch.drop_column("image_url")
        batch.drop_column("summary")
        batch.drop_column("can_attach_to_parent")
        batch.drop_column("independently_sellable")
        batch.drop_column("member_price_enabled")
        batch.drop_column("member_price_cents")
        batch.drop_column("store_price_cents")
        batch.drop_column("parent_project_id")
    op.drop_index("ix_service_lines_state", table_name="service_lines")
    op.drop_index("ix_service_lines_selection_revision_id", table_name="service_lines")
    op.drop_index("ix_service_lines_selection_session_id", table_name="service_lines")
    op.drop_table("service_lines")
    op.drop_index("ix_selection_change_requests_state", table_name="selection_change_requests")
    op.drop_index("ix_selection_change_requests_selection_revision_id", table_name="selection_change_requests")
    op.drop_index("ix_selection_change_requests_selection_session_id", table_name="selection_change_requests")
    op.drop_table("selection_change_requests")
    op.drop_index("ix_selection_revisions_state", table_name="selection_revisions")
    op.drop_index("ix_selection_revisions_selection_session_id", table_name="selection_revisions")
    op.drop_table("selection_revisions")
