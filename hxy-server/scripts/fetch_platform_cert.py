# -*- coding: utf-8 -*-
"""自动获取平台证书：调用微信支付平台证书下载接口，用 APIv3 密钥 AES-GCM 解密保存。
在 hxy-api 容器内执行: docker exec hxy-api python scripts/fetch_platform_cert.py
"""
import base64
import sys
import time
import uuid

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, "/app")  # 容器内代码目录（宿主为 /srv/hxy-server）
from app.core.config import settings  # noqa: E402
from app.services import wechatpay as wp  # noqa: E402

path = "/v3/certificates"
timestamp = str(int(time.time()))
nonce = uuid.uuid4().hex
body = ""
message = wp._build_message("GET", path, timestamp, nonce, body)
signature = wp._rsa_sign(message, wp._load_private_key())

headers = {
    "Authorization": (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{settings.wxpay_mchid}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.wxpay_cert_serial_no}"'
    ),
    "Wechatpay-Serial": settings.wxpay_cert_serial_no,
    "Accept": "application/json",
    "User-Agent": "hxy-miniapp/1.0",
}

resp = httpx.get(f"{wp.WXPAY_API}{path}", headers=headers, timeout=10)
print("HTTP", resp.status_code)
if resp.status_code != 200:
    print(resp.text[:400])
    sys.exit(1)

# 响应验签（公钥/平台证书双兼容）
try:
    wp._verify_response_signature(dict(resp.headers), resp.text)
    print("RESPONSE_SIGNATURE_OK")
except wp.WechatPayError as e:
    print("WARN response signature:", e)

saved = []
for cert_info in resp.json().get("data", []):
    enc = cert_info["encrypt_certificate"]
    aesgcm = AESGCM(settings.wxpay_apiv3_key.encode("utf-8"))
    plain = aesgcm.decrypt(
        enc["nonce"].encode("utf-8"),
        base64.b64decode(enc["ciphertext"]),
        enc["associated_data"].encode("utf-8"),
    )
    serial = cert_info["serial_no"]
    pem = plain.decode("utf-8")
    print(pem, end="")  # PEM 内容到 stdout，宿主重定向保存
    print(f"SAVED serial={serial} expire={cert_info.get('expire_time', '')}", file=sys.stderr)
    saved.append(serial)
print(f"TOTAL {len(saved)} certs -> stdout", file=sys.stderr)
