"""阿里云普通短信服务封装。"""
import json
from dataclasses import dataclass

from app.core.config import settings


class AliyunSmsError(Exception):
    pass


_client = None


@dataclass(frozen=True)
class SmsSendReceipt:
    biz_id: str | None
    request_id: str | None


def _get_client():
    global _client
    if _client is None:
        try:
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError:
            return None
        config = open_api_models.Config(
            access_key_id=settings.aliyun_sms_access_key_id,
            access_key_secret=settings.aliyun_sms_access_key_secret,
        )
        config.endpoint = "dysmsapi.aliyuncs.com"
        _client = Client(config)
    return _client


def send_sms_code(phone: str, code: str) -> SmsSendReceipt:
    client = _get_client()
    if client is None:
        raise AliyunSmsError("阿里云短信 SDK 未安装")
    from alibabacloud_dysmsapi20170525 import models as sms_models
    from alibabacloud_tea_util import models as util_models
    request = sms_models.SendSmsRequest(
        phone_numbers=phone,
        sign_name=settings.aliyun_sms_sign_name,
        template_code=settings.aliyun_sms_template_code,
        template_param=json.dumps({"code": code}, ensure_ascii=False),
    )
    try:
        response = client.send_sms_with_options(request, util_models.RuntimeOptions())
    except Exception as exc:
        raise AliyunSmsError(f"短信发送失败: {getattr(exc, 'message', '') or exc}") from exc
    body = response.body
    if getattr(body, "code", None) != "OK":
        raise AliyunSmsError(f"短信发送失败: {getattr(body, 'message', '') or '未知错误'}")
    return SmsSendReceipt(getattr(body, "biz_id", None), getattr(body, "request_id", None))
