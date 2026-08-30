"""H5 手机号登录的验证码记录。生产环境只保存哈希，不保存明文验证码。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerVerificationCode(Base):
    __tablename__ = "customer_verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_biz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sms_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
