import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import CouponTemplate, CustomerVerificationCode, Order, SelectionSession, ServiceFeedback, User, UserCoupon
from app.models.service import Visit
from app.schemas.auth import (
    BindPhoneRequest, H5LoginRequest, H5SendCodeRequest, H5SendCodeResponse,
    LoginRequest, LoginResponse, UserOut,
)
from app.services.aliyun_pnvs import AliyunPnvsError, send_sms_code as send_pnvs_code, verify_sms_code
from app.services.aliyun_sms import AliyunSmsError, send_sms_code as send_standard_sms_code
from app.services.wechat import code2session

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_phone(phone: str) -> str:
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=422, detail="请输入正确的手机号")
    return phone


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _hash_selection_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _latest_code(db: Session, phone: str) -> CustomerVerificationCode | None:
    return db.scalar(select(CustomerVerificationCode).where(
        CustomerVerificationCode.phone == phone,
    ).order_by(CustomerVerificationCode.sent_at.desc()))


@router.post("/h5/send-code", response_model=H5SendCodeResponse)
def send_h5_code(body: H5SendCodeRequest, db: Session = Depends(get_db)) -> H5SendCodeResponse:
    phone = _normalize_phone(body.phone)
    if settings.environment == "production" and not settings.h5_sms_debug and not (settings.aliyun_sms_enabled or settings.aliyun_pnvs_enabled):
        raise HTTPException(status_code=503, detail="短信服务尚未配置，请联系管理员")
    now = datetime.now(timezone.utc)
    latest = _latest_code(db, phone)
    if latest:
        sent_at = latest.sent_at.replace(tzinfo=timezone.utc) if latest.sent_at.tzinfo is None else latest.sent_at
        elapsed = (now - sent_at).total_seconds()
        if elapsed < settings.h5_sms_send_interval_seconds:
            wait_seconds = settings.h5_sms_send_interval_seconds - int(elapsed)
            raise HTTPException(status_code=429, detail={
                "code": "SMS_RATE_LIMITED", "message": f"请{wait_seconds}秒后再试",
            })
    if settings.aliyun_sms_enabled:
        # 普通短信路径：验证码由本服务生成，短信供应商只负责发送。
        code = f"{secrets.randbelow(1_000_000):06d}"
        try:
            receipt = send_standard_sms_code(phone, code)
        except AliyunSmsError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        record = CustomerVerificationCode(
            phone=phone,
            code_hash=_hash_code(code),
            expires_at=now + timedelta(seconds=settings.h5_sms_code_ttl_seconds),
            attempts=0,
            used_at=None,
        )
        # 新版模型记录供应商回执，旧本地演练模型没有这两列时仍可运行。
        if hasattr(record, "sms_biz_id"):
            record.sms_biz_id = receipt.biz_id
        if hasattr(record, "sms_request_id"):
            record.sms_request_id = receipt.request_id
        db.add(record)
        db.commit()
        return H5SendCodeResponse(sent=True, expires_in_seconds=settings.h5_sms_code_ttl_seconds, debug_code=None)
    if settings.aliyun_pnvs_enabled:
        # 生产路径：验证码由阿里云生成并发送，后端只记录发送时间用于限频。
        try:
            send_pnvs_code(phone)
        except AliyunPnvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        record = CustomerVerificationCode(
            phone=phone,
            code_hash="aliyun:managed",
            expires_at=now + timedelta(seconds=settings.h5_sms_code_ttl_seconds),
            attempts=0,
            used_at=None,
        )
        db.add(record)
        db.commit()
        return H5SendCodeResponse(
            sent=True,
            expires_in_seconds=settings.h5_sms_code_ttl_seconds,
            debug_code=None,
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    record = CustomerVerificationCode(
        phone=phone,
        code_hash=_hash_code(code),
        expires_at=now + timedelta(seconds=settings.h5_sms_code_ttl_seconds),
        attempts=0,
        used_at=None,
    )
    db.add(record)
    db.commit()
    debug_code = code if settings.h5_sms_debug or settings.environment in {"local", "test"} else None
    return H5SendCodeResponse(
        sent=True,
        expires_in_seconds=settings.h5_sms_code_ttl_seconds,
        debug_code=debug_code,
    )


@router.post("/h5/login", response_model=LoginResponse)
def h5_login(
    body: H5LoginRequest,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LoginResponse:
    phone = _normalize_phone(body.phone)
    selection_session = db.get(SelectionSession, body.selection_session_id) if body.selection_session_id else None
    if selection_session and not (
        x_selection_token
        and secrets.compare_digest(selection_session.access_token_hash, _hash_selection_token(x_selection_token))
    ):
        raise HTTPException(status_code=403, detail="选单访问凭证无效")
    record = _latest_code(db, phone)
    if not record or record.used_at is not None:
        raise HTTPException(status_code=400, detail="验证码无效，请重新获取")
    now = datetime.now(timezone.utc)
    expires_at = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    if now >= expires_at:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if record.attempts >= settings.h5_sms_max_attempts:
        raise HTTPException(status_code=400, detail="验证码错误次数已达上限，请重新获取")
    if record.code_hash.startswith("aliyun:"):
        # 生产路径：验证码由阿里云生成，交回阿里云核验。
        try:
            verified = verify_sms_code(phone, body.code)
        except AliyunPnvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        if not verified:
            record.attempts += 1
            db.commit()
            if record.attempts >= settings.h5_sms_max_attempts:
                raise HTTPException(status_code=400, detail="验证码错误次数已达上限，请重新获取")
            raise HTTPException(status_code=400, detail="验证码错误")
    elif not secrets.compare_digest(record.code_hash, _hash_code(body.code)):
        record.attempts += 1
        db.commit()
        if record.attempts >= settings.h5_sms_max_attempts:
            raise HTTPException(status_code=400, detail="验证码错误次数已达上限，请重新获取")
        raise HTTPException(status_code=400, detail="验证码错误")

    record.used_at = now
    openid = f"h5_{hashlib.sha256(phone.encode('utf-8')).hexdigest()[:32]}"
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid, phone=phone)
        db.add(user)
        db.flush()
        grant_new_user_coupons(db, user.id)
    else:
        user.phone = phone
    user.last_login_at = now
    if selection_session:
        session = selection_session
        if session.status in {"draft", "submitted", "confirmed"}:
            previous_customer_id = session.customer_id
            previous_customer = db.get(User, previous_customer_id) if previous_customer_id else None
            if previous_customer_id is None or (previous_customer and previous_customer.openid.startswith("anon_")):
                session.customer_id = user.id
                if previous_customer_id and previous_customer_id != user.id:
                    db.query(SelectionSession).filter(
                        SelectionSession.customer_id == previous_customer_id,
                        SelectionSession.status.in_(["draft", "submitted", "confirmed"]),
                    ).update({"customer_id": user.id}, synchronize_session=False)
                    # 浏览器 Cookie 只代表匿名浏览器实例，不能永久升级为手机号身份。
                    # 历史选单等业务记录可以合并到账号；后续新选单仍应默认匿名，
                    # 仅在顾客端携带登录令牌时显式绑定本次选单。
                    db.query(ServiceFeedback).filter(ServiceFeedback.customer_id == previous_customer_id).update(
                        {"customer_id": user.id}, synchronize_session=False
                    )
                    db.query(Visit).filter(Visit.user_id == previous_customer_id).update(
                        {"user_id": user.id}, synchronize_session=False
                    )
                    # 匿名身份下的券与订单一并归属到手机号账号。
                    db.query(UserCoupon).filter(UserCoupon.user_id == previous_customer_id).update(
                        {"user_id": user.id}, synchronize_session=False
                    )
                    db.query(Order).filter(Order.user_id == previous_customer_id).update(
                        {"user_id": user.id}, synchronize_session=False
                    )
            if session.customer_id == user.id and session.status == "draft":
                # 登录后的会员身份来自第三方同步数据；重算只用于门店结算参考。
                from app.api.selections import refresh_session_pricing
                refresh_session_pricing(db, session)
    db.commit()
    db.refresh(user)
    return LoginResponse(token=create_access_token(str(user.id), openid), user=UserOut.model_validate(user))


@router.get("/h5/me", response_model=UserOut)
def h5_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserOut:
    """刷新 H5 登录用户快照，确保后台刚开通的会员身份即时同步到顾客端。"""
    user = db.get(User, _current_user_id(authorization, db))
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return UserOut.model_validate(user)


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
