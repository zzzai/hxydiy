from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import CouponTemplate, User, UserCoupon
from app.schemas.auth import BindPhoneRequest, LoginRequest, LoginResponse, UserOut
from app.services.wechat import code2session

router = APIRouter(prefix="/auth", tags=["auth"])


def grant_new_user_coupons(db: Session, user_id: int) -> None:
    """新用户自动发券：发放所有 auto_grant_new_user 的已发布券模板。"""
    templates = db.scalars(select(CouponTemplate).where(
        CouponTemplate.auto_grant_new_user.is_(True),
        CouponTemplate.status == "published",
    ))
    for tpl in templates:
        exists = db.scalar(select(UserCoupon).where(
            UserCoupon.user_id == user_id, UserCoupon.template_id == tpl.id
        ))
        if exists:
            continue
        db.add(UserCoupon(
            user_id=user_id,
            template_id=tpl.id,
            status="unused",
            expire_at=datetime.now(timezone.utc) + timedelta(days=tpl.validity_days),
        ))


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """wx.login 登录：code 换 openid，首次登录自动注册用户并发放新人券。"""
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
        grant_new_user_coupons(db, user.id)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id), openid)
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.post("/bind-phone")
async def bind_phone(body: BindPhoneRequest) -> dict:
    """手机号绑定（getPhoneNumber code 解析，上线前接入）。"""
    raise HTTPException(status_code=501, detail="手机号绑定待上线前接入")


def _current_user_id(authorization: str | None, db: Session) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    from app.core.security import decode_token
    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    return int(payload["sub"])


@router.post("/bind-inviter")
async def bind_inviter(
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """邀请裂变：绑定邀请人（仅新用户可绑，只绑一次，不能邀请自己）。"""
    user_id = _current_user_id(authorization, db)
    inviter_id = body.get("inviter_id")
    if not inviter_id:
        raise HTTPException(status_code=400, detail="缺少邀请人")
    user = db.get(User, user_id)
    if user.inviter_id:
        return {"code": 0, "bound": False, "reason": "已绑定"}
    if int(inviter_id) == user.id:
        raise HTTPException(status_code=400, detail="不能邀请自己")
    inviter = db.get(User, int(inviter_id))
    if not inviter:
        raise HTTPException(status_code=404, detail="邀请人不存在")
    user.inviter_id = int(inviter_id)
    db.commit()
    return {"code": 0, "bound": True}
