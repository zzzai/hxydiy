from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerExternalIdentity(Base):
    """外部系统身份映射；手机号不是永久外部身份。"""

    __tablename__ = "customer_external_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_subject_id",
            name="uq_customer_external_identity_subject",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_subject_id: Mapped[str] = mapped_column(String(128))
    external_member_no: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
