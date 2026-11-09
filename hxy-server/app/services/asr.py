"""腾讯云 ASR 转写适配器。

只依赖 HTTPS + 标准库签名，不引入腾讯云 SDK。密钥未配置时保持可上传、
但转写状态为 not_configured，避免静默失败。
"""

from datetime import UTC, datetime
import hashlib
import hmac
import json
import time

import httpx

from app.core.config import settings

HOST = "asr.tencentcloudapi.com"
SERVICE = "asr"
VERSION = "2019-06-14"


class AsrNotConfigured(RuntimeError):
    pass


class AsrError(RuntimeError):
    pass


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def _authorization(action: str, payload: str, timestamp: int) -> str:
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{HOST}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join([
        "POST", "/", "", canonical_headers, signed_headers, _hash(payload.encode()),
    ])
    scope = f"{date}/{SERVICE}/tc3_request"
    string_to_sign = "\n".join([
        "TC3-HMAC-SHA256", str(timestamp), scope, _hash(canonical_request.encode()),
    ])
    secret_date = _hmac(("TC3" + settings.tencent_asr_secret_key).encode(), date)
    secret_service = _hmac(secret_date, SERVICE)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"TC3-HMAC-SHA256 Credential={settings.tencent_asr_secret_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _call(action: str, params: dict) -> dict:
    if not settings.asr_ready:
        raise AsrNotConfigured("ASR 未配置")
    payload = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    timestamp = int(time.time())
    headers = {
        "Authorization": _authorization(action, payload, timestamp),
        "Content-Type": "application/json; charset=utf-8",
        "Host": HOST,
        "X-TC-Action": action,
        "X-TC-Version": VERSION,
        "X-TC-Region": settings.tencent_asr_region,
        "X-TC-Timestamp": str(timestamp),
    }
    try:
        response = httpx.post(
            f"https://{HOST}", content=payload.encode(), headers=headers,
            timeout=httpx.Timeout(30, connect=10),
        )
    except httpx.HTTPError as exc:
        raise AsrError(f"ASR 网络错误: {exc}") from exc
    if response.status_code >= 400:
        raise AsrError(f"ASR HTTP {response.status_code}")
    body = response.json().get("Response", {})
    if body.get("Error"):
        raise AsrError(str(body["Error"].get("Message") or "ASR 调用失败"))
    return body


def transcribe_audio(audio_url: str) -> str:
    """提交腾讯云录音识别任务并轮询结果，返回纯文本。"""
    if not settings.asr_ready:
        raise AsrNotConfigured("ASR 未配置")
    created = _call("CreateRecTask", {
        "EngineModelType": settings.tencent_asr_engine,
        "ChannelNum": 1,
        "ResTextFormat": 0,
        "SourceType": 0,
        "Url": audio_url,
    })
    task_id = created.get("Data", {}).get("TaskId")
    if not task_id:
        raise AsrError("ASR 未返回任务编号")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        time.sleep(3)
        status = _call("DescribeTaskStatus", {"TaskId": int(task_id)})
        data = status.get("Data", {})
        state = data.get("Status")
        if state == 2:
            return str(data.get("Result") or "").strip()
        if state == 3:
            raise AsrError(str(data.get("ErrorMsg") or "ASR 转写失败"))
    raise AsrError("ASR 转写超时")
