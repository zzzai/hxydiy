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
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    publication_status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
