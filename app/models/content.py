from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PageContent(Base):
    """门店端页面配置。顾客端只读取 published 版本，后台负责发布。"""

    __tablename__ = "page_contents"
    __table_args__ = (UniqueConstraint("store_id", "page_key", name="uq_page_contents_store_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    page_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(128), default="到店选项目")
    subtitle: Mapped[str] = mapped_column(String(256), default="按需要，自由搭配")
    promo_banners: Mapped[list] = mapped_column(JSON, default=list)
    tea_options: Mapped[list] = mapped_column(JSON, default=list)
    coupon_prompt: Mapped[dict] = mapped_column(JSON, default=dict)
    brand_story: Mapped[dict] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
