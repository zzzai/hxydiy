"""微信支付 v3（直连商户 JSAPI）封装。

- 请求签名：商户 API 证书私钥 RSA-SHA256（Authorization: WECHATPAY2-SHA256-RSA2048）
- 回调验签：微信支付公钥模式（官方推荐，无过期时间）
- 回调解密：AES-256-GCM（APIv3 密钥）

凭证全部来自环境变量（.env），严禁入库。
"""

import base64
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

WXPAY_API = "https://api.mch.weixin.qq.com"


class WechatPayError(Exception):
    pass


def _load_private_key() -> Any:
    """加载商户 API 证书私钥（apiclient_key.pem）。"""
    with open(settings.wxpay_private_key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _load_public_key() -> Any:
    """加载微信支付公钥（验签用）。"""
    with open(settings.wxpay_public_key_path, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def _rsa_sign(data: str, private_key: Any) -> str:
    signature = private_key.sign(
        data.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return base64.b64encode(signature).decode()


def _rsa_verify(data: str, signature_b64: str, public_key: Any) -> bool:
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            data.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def _build_message(method: str, url_path: str, timestamp: str, nonce: str,
                   body: str) -> str:
    return f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"


def _request_headers(method: str, url_path: str, body: str) -> dict:
    """生成带商户签名的请求头（商户 API 证书私钥签名）。"""
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    message = _build_message(method, url_path, timestamp, nonce, body)
    signature = _rsa_sign(message, _load_private_key())
    return {
        "Authorization": (
            'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{settings.wxpay_mchid}",'
            f'nonce_str="{nonce}",'
            f'signature="{signature}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{settings.wxpay_cert_serial_no}"'
        ),
        # 微信支付公钥模式：商户请求时声明签名所用证书序列号（微信支付据此验商户请求签名）
        "Wechatpay-Serial": settings.wxpay_cert_serial_no,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "hxy-miniapp/1.0",
    }


def _verify_response_signature(headers: dict, body: str) -> None:
    """响应验签：用微信支付公钥验证微信支付应答的真实性。"""
    serial = headers.get("wechatpay-serial", "")
    timestamp = headers.get("wechatpay-timestamp", "")
    nonce = headers.get("wechatpay-nonce", "")
    signature = headers.get("wechatpay-signature", "")
    if not all([serial, timestamp, nonce, signature]):
        raise WechatPayError("响应缺少验签头")
    if serial != settings.wxpay_public_key_id:
        raise WechatPayError(f"响应序列号不匹配: {serial}")
    if abs(int(time.time()) - int(timestamp)) > 300:
        raise WechatPayError("响应时间戳超时")
    message = _build_message("", "", timestamp, nonce, body)
    if not _rsa_verify(message, signature, _load_public_key()):
        raise WechatPayError("响应验签失败")


def _ensure_configured() -> None:
    missing = [
        name for name, val in {
            "WXPAY_MCHID": settings.wxpay_mchid,
            "WXPAY_APIV3_KEY": settings.wxpay_apiv3_key,
            "WXPAY_CERT_SERIAL_NO": settings.wxpay_cert_serial_no,
            "WXPAY_PRIVATE_KEY_PATH": settings.wxpay_private_key_path,
            "WXPAY_PUBLIC_KEY_ID": settings.wxpay_public_key_id,
            "WXPAY_PUBLIC_KEY_PATH": settings.wxpay_public_key_path,
        }.items() if not val
    ]
    if missing:
        raise WechatPayError(f"支付凭证未配置: {', '.join(missing)}")


async def create_jsapi_payment(out_trade_no: str, description: str,
                               amount_cents: int, openid: str) -> dict:
    """JSAPI 统一下单，返回小程序端调起支付参数。

    amount_cents: 金额（分）
    """
    _ensure_configured()
    path = "/v3/pay/transactions/jsapi"
    body = json.dumps({
        "appid": settings.wxpay_appid,
        "mchid": settings.wxpay_mchid,
        "description": description[:127],
        "out_trade_no": out_trade_no,
        "notify_url": settings.wxpay_notify_url,
        "amount": {"total": amount_cents, "currency": "CNY"},
        "payer": {"openid": openid},
    }, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{WXPAY_API}{path}",
            headers=_request_headers("POST", path, body),
            content=body,
        )
    _verify_response_signature(dict(resp.headers), resp.text)
    if resp.status_code != 200:
        raise WechatPayError(f"统一下单失败 {resp.status_code}: {resp.text[:200]}")

    prepay_id = resp.json()["prepay_id"]

    # 小程序端调起参数：appId/timeStamp/nonceStr/package/signType/paySign
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    sign_str = (
        f"{settings.wxpay_appid}\n{timestamp}\n{nonce}\n{package}\n"
    )
    pay_sign = _rsa_sign(sign_str, _load_private_key())
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


async def verify_and_decrypt_notify(headers: dict, raw_body: bytes) -> dict:
    """回调验签（微信支付公钥模式）+ AES-256-GCM 解密，返回业务资源 dict。"""
    _ensure_configured()
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth.startswith("WECHATPAY2-SHA256-RSA2048"):
        raise WechatPayError("回调认证头缺失")

    params = {}
    for part in auth.replace("WECHATPAY2-SHA256-RSA2048", "").strip().split(","):
        key, _, value = part.strip().partition("=")
        params[key] = value.strip('"')

    signature = params.get("signature", "")
    serial = params.get("serial_no", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce_str", "")

    if serial != settings.wxpay_public_key_id:
        raise WechatPayError(f"回调证书序列号不匹配: {serial}")

    # 时间戳防重放（5 分钟窗口）
    if abs(int(time.time()) - int(timestamp)) > 300:
        raise WechatPayError("回调时间戳超时")

    message = _build_message("POST", "/api/v1/payments/notify", timestamp, nonce,
                             raw_body.decode("utf-8"))
    if not _rsa_verify(message, signature, _load_public_key()):
        raise WechatPayError("回调验签失败")

    # 解密 resource（AES-256-GCM，密钥 = APIv3 密钥）
    resource = json.loads(raw_body)["resource"]
    ciphertext = base64.b64decode(resource["ciphertext"])
    aesgcm = AESGCM(settings.wxpay_apiv3_key.encode("utf-8"))
    plaintext = aesgcm.decrypt(
        resource["nonce"].encode("utf-8"),
        ciphertext,
        resource["associated_data"].encode("utf-8"),
    )
    return json.loads(plaintext)
