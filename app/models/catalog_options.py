"""版本化项目目录、混合选项和选项价格。"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


CHOICE_TYPES = {"preference", "linked_project", "dedicated_charge"}
CHARGE_MODES = {"free", "inherit_linked_price", "custom_price"}


class ProjectCatalogVersion(Base):
    __tablename__ = "project_catalog_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_catalog_version"),
        CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_project_catalog_version_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class ProjectOptionGroup(Base):
    __tablename__ = "project_option_groups"
    __table_args__ = (
        UniqueConstraint("catalog_version_id", "code", name="uq_project_option_group_code"),
        CheckConstraint(
            "selection_mode IN ('single', 'multiple')",
            name="ck_project_option_group_selection_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_version_id: Mapped[int] = mapped_column(
        ForeignKey("project_catalog_versions.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(512), default="")
    selection_mode: Mapped[str] = mapped_column(String(16), default="single")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class ProjectOptionChoice(Base):
    __tablename__ = "project_option_choices"
    __table_args__ = (
        UniqueConstraint("option_group_id", "code", name="uq_project_option_choice_code"),
        CheckConstraint(
            "choice_type IN ('preference', 'linked_project', 'dedicated_charge')",
            name="ck_project_option_choice_type",
        ),
        CheckConstraint(
            "charge_mode IN ('free', 'inherit_linked_price', 'custom_price')",
            name="ck_project_option_choice_charge_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    option_group_id: Mapped[int] = mapped_column(ForeignKey("project_option_groups.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(512), default="")
    choice_type: Mapped[str] = mapped_column(String(24))
    linked_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    charge_mode: Mapped[str] = mapped_column(String(24))
    independently_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    coupon_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    annual_gift_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    qualifies_for_foot_bath_bundle: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)


class OptionChoicePrice(Base):
    __tablename__ = "option_choice_prices"
    __table_args__ = (
        UniqueConstraint(
            "option_choice_id",
            "price_type",
            "effective_from",
            name="uq_option_choice_price_effective",
        ),
        CheckConstraint(
            "price_type IN ('store', 'group', 'member')",
            name="ck_option_choice_price_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    option_choice_id: Mapped[int] = mapped_column(ForeignKey("project_option_choices.id"), index=True)
    price_type: Mapped[str] = mapped_column(String(16), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
