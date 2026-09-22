# 目录模块：项目、价格表、加项、品牌模板

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProjectTemplate(Base):
    """品牌总部项目模板（MULTI-STORE-005）：门店项目的主数据来源。
    品牌级内容仅总部可改；brand_enabled=false 时全部门店不得上架。"""

    __tablename__ = "project_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desc: Mapped[str] = mapped_column(String(512), default="")
    image_url: Mapped[str] = mapped_column(String(512), default="")
    detail_modules: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    brand_enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TemplatePricePolicy(Base):
    """模板价格政策：总部标准价 + 门店覆盖规则（对齐 BRAND-CATALOG-004 §5.2）。
    每个模板每种价格类型（store/member/group）至多一条。"""

    __tablename__ = "template_price_policies"
    __table_args__ = (
        CheckConstraint("price_type IN ('store', 'member', 'group')", name="ck_template_price_policies_type"),
        CheckConstraint("standard_price_cents >= 0", name="ck_template_price_policies_standard_non_negative"),
        UniqueConstraint("template_id", "price_type", name="uq_template_price_policies_template_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("project_templates.id"), index=True)
    price_type: Mapped[str] = mapped_column(String(16), index=True)  # store / member / group
    standard_price_cents: Mapped[int] = mapped_column(Integer)
    override_allowed: Mapped[bool] = mapped_column(default=True)
    min_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    force_standard: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StorePriceOverride(Base):
    """门店覆盖价：挂在门店项目实例上，(project_id, price_type) 唯一。
    有效价解析（PR2 实现）：force_standard → 标准价；允许覆盖且本店值在
    [min, max] 区间内 → 覆盖价；否则标准价。"""

    __tablename__ = "store_price_overrides"
    __table_args__ = (
        CheckConstraint("price_type IN ('store', 'member', 'group')", name="ck_store_price_overrides_type"),
        CheckConstraint("override_price_cents >= 0", name="ck_store_price_overrides_non_negative"),
        UniqueConstraint("project_id", "price_type", name="uq_store_price_overrides_project_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    price_type: Mapped[str] = mapped_column(String(16))
    override_price_cents: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_published_version_id"],
            ["project_catalog_versions.project_id", "project_catalog_versions.id"],
            name="fk_projects_current_published_version_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement="ignore_fk")
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)  # bath/balance/care/kit/tea...
    category_mark: Mapped[str] = mapped_column(String(8), default="")
    name: Mapped[str] = mapped_column(String(64))
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String(512), default="")
    image_url: Mapped[str] = mapped_column(String(512), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # H5/小程序详情页的可排序内容模块，例如图片、标题、正文、卖点。
    detail_modules: Mapped[list] = mapped_column(JSON, default=list)
    # DIY 选项由后端发布；价格仍以项目/加项价格表为准。
    diy_options: Mapped[list] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    price_label: Mapped[str] = mapped_column(String(32), default="")
    # 品牌模板关联（MULTI-STORE-005）：迁移期按 code 一对一回填，历史引用不变。
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_templates.id"), nullable=True, index=True
    )
    # 会员价开关（与 addons 语义一致）：关闭时该项目会员价不对顾客生效。
    member_price_enabled: Mapped[bool] = mapped_column(default=False)
    # draft / candidate / published / archived —— 只有 published 可被顾客端看到
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    content_version: Mapped[str] = mapped_column(String(32), default="")
    current_published_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PriceBook(Base):
    """价格表：一个项目多价格源（store 门店价 / group 团购价 / member 会员价）。
    价格只从本表读，不信任前端。"""

    __tablename__ = "price_book"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_price_book_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    price_type: Mapped[str] = mapped_column(String(16), index=True)  # store / group / member
    amount_cents: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(32), default="v1")
    publisher: Mapped[str] = mapped_column(String(64), default="system")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 保留价格历史；为空表示当前有效，填充后表示该版本已停用。
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Addon(Base):
    __tablename__ = "addons"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    parent_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String(512), default="")
    image_url: Mapped[str] = mapped_column(String(512), default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # 免费选项仅记录服务偏好；收费加项才会写入服务端报价和线下结算参考金额。
    chargeable: Mapped[bool] = mapped_column(default=True)
    store_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    member_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    member_price_enabled: Mapped[bool] = mapped_column(default=False)
    independently_sellable: Mapped[bool] = mapped_column(default=False)
    can_attach_to_parent: Mapped[bool] = mapped_column(default=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """门店商品目录；当前仅展示，不承诺线上交易或履约。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    desc: Mapped[str] = mapped_column(String(256), default="")
    spec: Mapped[str] = mapped_column(String(64), default="")
    product_type: Mapped[str] = mapped_column(String(16), index=True)  # foot/heat/gift
    price_cents: Mapped[int] = mapped_column(Integer)
    member_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 会员价开关（catalog-closure backlog 立项）：关闭时 member_price_cents 不生效。
    member_price_enabled: Mapped[bool] = mapped_column(default=False)
    image_url: Mapped[str] = mapped_column(String(512), default="")
    detail_modules: Mapped[list] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
