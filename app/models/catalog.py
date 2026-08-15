# 目录模块：项目、价格表、加项

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    # draft / candidate / published / archived —— 只有 published 可被顾客端看到
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    content_version: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PriceBook(Base):
    """价格表：一个项目多价格源（store 门店价 / group 团购价 / member 会员价）。
    价格只从本表读，不信任前端。"""

    __tablename__ = "price_book"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    price_type: Mapped[str] = mapped_column(String(16), index=True)  # store / group / member
    amount_cents: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(32), default="v1")
    publisher: Mapped[str] = mapped_column(String(64), default="system")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    """商城商品（到店自提；定价 9.9 暂定，待门店复核）。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    desc: Mapped[str] = mapped_column(String(256), default="")
    spec: Mapped[str] = mapped_column(String(64), default="")
    product_type: Mapped[str] = mapped_column(String(16), index=True)  # foot/heat/gift
    price_cents: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str] = mapped_column(String(512), default="")
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
