"""外部系统集成接口。当前仅接收第三方会员状态，不承担收款或发卡。"""

import hashlib
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User

router = APIRouter(prefix="/integrations", tags=["integrations"])


class MembershipSyncIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    is_member: bool
    member_type: str | None = Field(default=None, max_length=16)


@router.post("/memberships/sync")
def sync_membership(
    body: MembershipSyncIn,
    x_membership_sync_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """第三方按手机号推送会员状态；H5 登录后读取本地同步结果。"""
    if not settings.third_party_membership_sync_key:
        raise HTTPException(status_code=503, detail="第三方会员同步尚未配置")
    if x_membership_sync_key != settings.third_party_membership_sync_key:
        raise HTTPException(status_code=401, detail="会员同步凭证无效")
    if not re.fullmatch(r"1[3-9]\d{9}", body.phone):
        raise HTTPException(status_code=422, detail="请输入正确的手机号")

    user = db.scalar(select(User).where(User.phone == body.phone))
    if user is None:
        openid = f"h5_{hashlib.sha256(body.phone.encode('utf-8')).hexdigest()[:32]}"
        user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid, phone=body.phone)
        db.add(user)
    user.phone = body.phone
    user.is_member = body.is_member
    user.member_type = body.member_type if body.is_member else None
    db.commit()
    db.refresh(user)
    return {
        "phone": user.phone,
        "is_member": user.is_member,
        "member_type": user.member_type,
    }
