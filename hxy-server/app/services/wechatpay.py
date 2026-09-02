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
from cryptography import x509
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


def _load_platform_cert() -> Any | None:
    """加载平台证书公钥（灰度兼容，可选）。"""
    if not settings.wxpay_platform_cert_path:
        return None
    try:
        with open(settings.wxpay_platform_cert_path, "rb") as f:
            return x509.load_pem_x509_certificate(f.read()).public_key()
    except Exception:
        return None


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
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "hxy-miniapp/1.0",
    }


def _verify_by_serial(serial: str, message: str, signature_b64: str) -> bool:
    """按序列号选择验签密钥：公钥 ID -> 微信支付公钥；平台证书序列号 -> 平台证书。"""
    if serial == settings.wxpay_public_key_id:
        return _rsa_verify(message, signature_b64, _load_public_key())
    platform_cert = _load_platform_cert()
    if platform_cert is not None:
        return _rsa_verify(message, signature_b64, platform_cert)
    return False


def _header(headers: dict, name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return ""


def _response_message(timestamp: str, nonce: str, body: str) -> str:
    return f"{timestamp}\n{nonce}\n{body}\n"


def _verify_response_signature(headers: dict, body: str) -> None:
    """严格验证微信支付 APIv3 响应签名。"""
    serial = _header(headers, "Wechatpay-Serial")
    timestamp = _header(headers, "Wechatpay-Timestamp")
    nonce = _header(headers, "Wechatpay-Nonce")
    signature = _header(headers, "Wechatpay-Signature")
    if not all([serial, timestamp, nonce, signature]):
        raise WechatPayError("响应缺少验签头")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise WechatPayError("响应时间戳无效") from exc
    if abs(int(time.time()) - timestamp_value) > 300:
        raise WechatPayError("响应时间戳超时")
    message = _response_message(timestamp, nonce, body)
    if not _verify_by_serial(serial, message, signature):
        raise WechatPayError(f"响应验签失败 serial={serial}")


def _ensure_configured() -> None:
    missing = [
        name for name, val in {
            "WXPAY_MCHID": settings.wxpay_mchid,
            "WXPAY_APPID": settings.wxpay_appid,
            "WXPAY_APIV3_KEY": settings.wxpay_apiv3_key,
            "WXPAY_CERT_SERIAL_NO": settings.wxpay_cert_serial_no,
            "WXPAY_PRIVATE_KEY_PATH": settings.wxpay_private_key_path,
            "WXPAY_PUBLIC_KEY_ID": settings.wxpay_public_key_id,
            "WXPAY_PUBLIC_KEY_PATH": settings.wxpay_public_key_path,
            "WXPAY_NOTIFY_URL": settings.wxpay_notify_url,
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
    serial = _header(headers, "Wechatpay-Serial")
    timestamp = _header(headers, "Wechatpay-Timestamp")
    nonce = _header(headers, "Wechatpay-Nonce")
    signature = _header(headers, "Wechatpay-Signature")
    if not all([serial, timestamp, nonce, signature]):
        raise WechatPayError("回调缺少验签头")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise WechatPayError("回调时间戳无效") from exc

    # 时间戳防重放（5 分钟窗口）
    if abs(int(time.time()) - timestamp_value) > 300:
        raise WechatPayError("回调时间戳超时")

    message = _response_message(timestamp, nonce, raw_body.decode("utf-8"))
    # 灰度期双兼容：公钥 ID -> 微信支付公钥；平台证书序列号 -> 平台证书
    if not _verify_by_serial(serial, message, signature):
        raise WechatPayError(f"回调验签失败 serial={serial}")

    # 解密 resource（AES-256-GCM，密钥 = APIv3 密钥）
    resource = json.loads(raw_body)["resource"]
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        raise WechatPayError("不支持的回调加密算法")
    ciphertext = base64.b64decode(resource["ciphertext"])
    aesgcm = AESGCM(settings.wxpay_apiv3_key.encode("utf-8"))
    plaintext = aesgcm.decrypt(
        resource["nonce"].encode("utf-8"),
        ciphertext,
        resource.get("associated_data", "").encode("utf-8"),
    )
    return json.loads(plaintext)
