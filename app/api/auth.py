from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import BindPhoneRequest, LoginRequest, LoginResponse, UserOut
from app.services.wechat import code2session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """wx.login 登录：code 换 openid，首次登录自动注册用户。"""
    if not settings.wx_appsecret:
        # 本地/测试环境未配置 AppSecret 时，允许用 code 直接作为 openid 前缀调试
        openid = f"dev_{body.code[:24]}" if body.code else "dev_anonymous"
    else:
        openid = (await code2session(body.code))["openid"]

    user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid)
        db.add(user)
        db.flush()
    from datetime import datetime, timezone

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id), openid)
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.post("/bind-phone")
async def bind_phone(body: BindPhoneRequest) -> dict:
    """手机号绑定（getPhoneNumber code 解析，上线前接入）。"""
    raise HTTPException(status_code=501, detail="手机号绑定待上线前接入")
